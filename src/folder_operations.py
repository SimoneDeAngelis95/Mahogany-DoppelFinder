"""Folder action selection, confirmation, execution and result reporting.

This mixin uses the comparison dialog's roots, result and selection, and owns
its transfer lifecycle. Filesystem planning lives in folder_actions.
"""
import os
from pathlib import Path
import threading

from PyQt6.QtCore import QFile, QThreadPool, Qt, QStandardPaths
from PyQt6.QtWidgets import (QFileDialog, QMessageBox, QDialog, QDialogButtonBox,
                            QFormLayout, QLineEdit, QComboBox, QLabel, QVBoxLayout)

from comparison_results import update_results
from comparison_jobs import ActionJob
from file_transfers import copy_without_overwrite
from filefile_window import file_signature, move_without_overwrite
from folder_actions import (merged_entries, validate_merge_target, check_destination,
                            resolve_plan, execute_plan, check_transfer_space, STOPPED_REASON)

def bulk_entries(result, side, scope, media='all'):
    """Select the completed scan, never the current tree selection or unverified files."""
    if side not in ('A', 'B') or scope not in ('matching', 'unique'):
        raise ValueError('Unsupported whole-folder action')
    if media not in ('all', 'images', 'audio', 'video'):
        raise ValueError('Unsupported media filter')
    if not result:
        return []
    key = 'common' if scope == 'matching' else ('only_a' if side == 'A' else 'only_b')
    other = 'B' if side == 'A' else 'A'
    selected = {}
    for group in result[key]:
        for entry in group[side]:
            kind = 'images' if entry['kind'] in ('image', 'animation') else entry['kind']
            if media != 'all' and media != kind:
                continue
            keep = group[other] if scope == 'matching' else []
            # In overlapping roots, the very same path can appear on both sides.
            # It cannot be removed from A while keeping that path in B.
            path = os.path.realpath(entry['path'])
            if any(os.path.realpath(copy['path']) == path for copy in keep):
                continue
            selected[path] = dict(entry, keep_copies=list(keep))
    return list(selected.values())


def not_compared_entry(note):
    """Attach a deletion snapshot only to an existing regular, non-link file."""
    path = Path(note['path'])
    try:
        if path.is_symlink() or not path.is_file():
            return None
        return dict(note, kind='uncompared', not_compared=True,
                    signature=file_signature(path))
    except OSError:
        return None


def verify_bulk_entry(entry):
    if Path(entry['path']).is_symlink() or file_signature(entry['path']) != entry['signature']:
        raise ValueError('File changed. Scan again.')
    for copy in entry.get('keep_copies', []):
        if Path(copy['path']).is_symlink() or file_signature(copy['path'])[:4] != copy['signature'][:4]:
            raise ValueError('A matching copy in the other folder changed or disappeared. Scan again.')


def run_folder_action(operation, plan, policy, skipped, renamed, is_bulk,
                      destination_root, roots, cancel, progress, snapshots=None):
    """Recheck and execute an approved batch; stop only between files.

    Return (batch_result, created_merge_root). This worker never accesses UI.
    Source and keeper checks happen before C creation and again per file.
    """
    created_merge_root = False
    # Recheck every approved source before making any changes. Name
    # collisions are recoverable; changed sources and keepers are not.
    try:
        if is_bulk:
            for entry, _ in plan:
                if cancel.is_set():
                    return ([], [], skipped+[(e,d,STOPPED_REASON) for e,d in plan], []), created_merge_root
                verify_bulk_entry(entry)
        if cancel.is_set():
            return ([], [], skipped+[(e,d,STOPPED_REASON) for e,d in plan], []), created_merge_root
        check_transfer_space(plan, operation)
        if destination_root:
            validate_merge_target(destination_root, roots)
            if cancel.is_set():
                return ([], [], skipped+[(e,d,STOPPED_REASON) for e,d in plan], []), created_merge_root
            Path(destination_root).mkdir(exist_ok=False)
            created_merge_root = True
    except (OSError, ValueError) as error:
        return ([], ['Nothing was changed: '+str(error)], skipped, []), created_merge_root
    if operation != 'trash':
        primitive = copy_without_overwrite if operation=='copy' else move_without_overwrite
        def transfer(source, destination, expected):
            value = primitive(source, destination, expected)
            if snapshots is not None:
                try:
                    signature = file_signature(destination)
                    snapshots[str(destination)] = signature if signature[2:4] == expected[2:4] else None
                except OSError:
                    snapshots[str(destination)] = None
            return value
        return execute_plan(plan, policy, transfer, verify_bulk_entry, skipped, renamed, progress, cancel), created_merge_root
    successes = []
    errors = []
    stopped = []
    for index, (entry, _) in enumerate(plan, 1):
        if cancel.is_set():
            stopped.extend((e, d, STOPPED_REASON) for e,d in plan[index-1:])
            break
        try:
            verify_bulk_entry(entry)
            file = QFile(entry['path'])
            if not file.moveToTrash():
                raise OSError(file.errorString() or 'System Trash unavailable')
            successes.append((entry['path'], 'System Trash'))
        except Exception as error:
            errors.append(entry['path']+': '+str(error))
        progress(index, len(plan))
    return (successes, errors, stopped, []), created_merge_root


class FolderOperations:
    """Actions on selected files, whole folders and merged folder C."""

    def _bulk_controls(self):
        if not hasattr(self, 'bulk_menu_actions'):
            return
        ready = bool(self.result) and not self.busy and not self.action_active
        self.bulk_media.setEnabled(ready)
        category = self.bulk_media.currentData()
        counts = {}
        for side in ('A', 'B'):
            other = 'B' if side == 'A' else 'A'
            matching = len(bulk_entries(self.result, side, 'matching', category))
            unique = len(bulk_entries(self.result, side, 'unique', category))
            counts[side] = (matching, unique)
            labels = {
                'trash': f'Move all matching files in {side} to Trash ({matching})',
                'move': f'Move files only in {side} to {other} ({unique})',
                'copy': f'Copy files only in {side} to {other} ({unique})',
            }
            for operation, text in labels.items():
                action = self.bulk_menu_actions[(side, operation)]
                action.setText(text)
                action.setEnabled(ready and (matching if operation == 'trash' else unique) > 0)
            self.bulk_buttons[side].setEnabled(ready and (matching + unique) > 0)
        if ready:
            nesting = 'including subfolders' if self.recursive else 'top-level files only'
            self.bulk_hint.setText(f'A: {counts["A"][0]} matching · {counts["A"][1]} unique    |    B: {counts["B"][0]} matching · {counts["B"][1]} unique. Applies to the completed scan, {nesting}. Unverified files are excluded.')
        else:
            self.bulk_hint.setText('Available after a complete scan. Choose a media type, then an action for A or B.')

    def _bulk_action(self, side, operation, scope):
        if self.busy or self.action_active or not self.result:
            return
        if (operation, scope) not in (('trash', 'matching'), ('move', 'unique'), ('copy', 'unique')):
            raise ValueError('Unsupported whole-folder action')
        entries = bulk_entries(self.result, side, scope, self.bulk_media.currentData())
        label = f'Folder {side} · {self.bulk_media.currentText()} · '+('matching content' if scope == 'matching' else f'files only in {side}')
        self._action(operation, entries, label)

    def _choose_conflicts(self, conflicts):
        dialog = QMessageBox(self)
        dialog.setWindowTitle('Destination name conflicts')
        dialog.setIcon(QMessageBox.Icon.Question)
        dialog.setText(f'{len(conflicts)} file(s) have destination name conflicts. Choose how to handle them for this operation.\n\nExisting files will never be overwritten. Ignore leaves those source files untouched.')
        dialog.setDetailedText('\n\n'.join(e['path']+'\n  → '+str(d)+'\n'+reason for e,d,reason in conflicts))
        rename = dialog.addButton('Rename automatically', QMessageBox.ButtonRole.ActionRole)
        ignore = dialog.addButton('Ignore conflicting files', QMessageBox.ButtonRole.ActionRole)
        dialog.addButton(QMessageBox.StandardButton.Cancel)
        dialog.setDefaultButton(QMessageBox.StandardButton.Cancel)
        dialog.exec()
        if dialog.clickedButton() == rename:
            return 'rename'
        if dialog.clickedButton() == ignore:
            return 'skip'
        return None

    def _choose_merge_options(self):
        """Choose a name and the source of shared content in one dialog."""
        dialog = QDialog(self)
        dialog.setWindowTitle('Create folder C')
        layout = QVBoxLayout(dialog)
        form = QFormLayout()
        name = QLineEdit('Mahogany merged')
        name.setObjectName('mergeName')
        copies = QComboBox()
        copies.setObjectName('mergeSharedSide')
        copies.addItem('Keep copies from A', 'A')
        copies.addItem('Keep copies from B', 'B')
        form.addRow('New folder name:', name)
        form.addRow('Content present in both folders:', copies)
        layout.addLayout(form)
        explanation = QLabel('Files found only in A or B are always included.\nInternal copies and subfolders are preserved.\nUses all verified scanned media, independently of the A/B filter.')
        explanation.setWordWrap(True)
        layout.addWidget(explanation)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        name.selectAll()
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return None
        return name.text().strip(), copies.currentData()

    def _create_merged_folder(self):
        if self.busy or self.action_active or not self.result:
            return
        desktop = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DesktopLocation)
        parent = QFileDialog.getExistingDirectory(self, 'Choose where to create folder C',
                                                  desktop or str(Path.home() / 'Desktop'))
        if not parent:
            return
        options = self._choose_merge_options()
        if options is None:
            return
        name, shared_side = options
        name = name.strip()
        if not name or name in ('.', '..') or '/' in name or '\\' in name:
            QMessageBox.warning(self, 'Choose a folder name', 'Enter a single folder name without path separators.')
            return
        try:
            destination = validate_merge_target(Path(parent) / name, self.roots)
        except (OSError, ValueError) as error:
            QMessageBox.warning(self, 'Choose another destination', str(error))
            return
        uncertain = sum(len(g['A'])+len(g['B']) for g in self.result['uncertain'])
        label = ('Create folder C: '+str(destination)+'\n'
                 f'Copy all occurrences from {shared_side} for shared content, plus all files exclusive to A or B. '
                 'Internal copies and relative subfolders are preserved. A and B remain unchanged.\n'
                 f'{uncertain} unverified result file(s) and {len(self.result["notes"])} not-compared entries are excluded. '
                 'Uses every media type included in the completed scan.')
        self._action('copy', merged_entries(self.result, shared_side), label, destination)

    def _show_operation_report(self, title, message, details, warning=False):
        dialog = QMessageBox(self)
        dialog.setWindowTitle(title)
        dialog.setIcon(QMessageBox.Icon.Warning if warning else QMessageBox.Icon.Information)
        dialog.setTextFormat(Qt.TextFormat.PlainText)
        dialog.setText(message)
        dialog.setDetailedText(details)
        dialog.setStandardButtons(QMessageBox.StandardButton.Ok)
        dialog.exec()

    def _prepare_action_requests(self, operation, entries, destination_root):
        """Validate selected snapshots and preserve paths relative to each root."""
        identities = set()
        requests = []
        invalid = []
        for entry in entries:
            source = Path(entry['path'])
            destination = None
            if os.path.realpath(source) in identities:
                continue
            identities.add(os.path.realpath(source))
            try:
                verify_bulk_entry(entry)
                if operation != 'trash':
                    source_root = Path(self.roots['AB'.index(entry['side'])])
                    target_root = Path(destination_root) if destination_root else Path(self.roots[1-'AB'.index(entry['side'])])
                    destination = target_root / source.relative_to(source_root)
                    check_destination(destination)
                    if source.absolute() == destination.absolute():
                        raise ValueError('Source and destination are the same')
                requests.append((entry, destination))
            except (OSError, ValueError) as error:
                invalid.append(str(source)+': '+str(error))
        return requests, invalid

    def _action(self, operation, entries=None, scope_label=None, destination_root=None):
        if self.busy or self.action_active:
            return
        is_bulk = entries is not None
        entries = list(entries) if is_bulk else self._selection()
        if not entries:
            return
        if operation != 'trash' and any(e.get('not_compared') for e in entries):
            QMessageBox.information(self, 'File not compared', 'Uncompared files can be opened or moved to Trash. Copy and move actions require a verified comparison.')
            return
        selected = self.tabs.currentWidget().selectedItems()
        if not is_bulk and any('entry' not in (item.data(0, Qt.ItemDataRole.UserRole) or {}) for item in selected):
            QMessageBox.information(self, 'Select individual files', 'Select the file rows you want to act on, rather than the whole content group.')
            return
        requests, invalid = self._prepare_action_requests(operation, entries, destination_root)
        if invalid:
            QMessageBox.warning(self, 'Scan again before proceeding', 'Nothing was changed.\n\n'+'\n'.join(invalid[:12]))
            return
        skipped = []
        renamed = []
        policy = 'skip'
        plan = requests
        if operation != 'trash':
            try:
                plan, skipped, renamed = resolve_plan(requests)
                if skipped:
                    policy = self._choose_conflicts(skipped)
                    if policy is None:
                        return
                    plan, skipped, renamed = resolve_plan(requests, policy)
            except (OSError, ValueError) as error:
                QMessageBox.warning(self, 'Unsafe destination', 'Nothing was changed.\n\n'+str(error))
                return
        if not plan:
            self._show_operation_report('No files to transfer', f'All {len(skipped)} file(s) were ignored. Nothing was changed.',
            '\n\n'.join(e['path']+'\n  → '+str(d)+'\n'+reason for e,d,reason in skipped))
            return
        try:
            check_transfer_space(plan, operation)
        except (OSError, ValueError) as error:
            QMessageBox.warning(self, 'Destination space unavailable', str(error))
            return
        verb = {'copy': 'Copy', 'move': 'Move', 'trash': 'Move to Trash'}[operation]
        lines = [e['path']+(('\n  → '+str(d)) if d else '') for e,d in plan]
        skip_lines = [e['path']+'\n  → '+str(d)+'\n  Ignored: '+reason for e,d,reason in skipped]
        total_bytes = sum(e['signature'][2] for e, _ in plan)
        size_mb = total_bytes / 1_000_000
        message = f'{verb} {len(plan)} file(s) · {size_mb:,.1f} MB?'
        if destination_root:
            message = f'Create folder C with {len(plan)} file(s) · {size_mb:,.1f} MB?'
            message += '\nA and B will remain unchanged.'
        elif operation == 'trash':
            message += '\nSelected files will go to the system Trash.'
        else:
            message += '\nExisting files will never be overwritten.'
        if operation == 'trash' and any(e.get('not_compared') for e, _ in plan):
            message += '\nNo matching copy has been verified for these files.'
        if skipped or renamed:
            message += f'\n{len(skipped)} ignored · {len(renamed)} automatically renamed.'
        details = []
        if scope_label:
            details.append(scope_label)
        details.append(f'{len(plan)} file(s) · {total_bytes:,} bytes')
        if operation == 'trash':
            if any(e.get('not_compared') for e, _ in plan):
                details.append('These files were not compared. No matching copy is guaranteed to remain.')
            elif is_bulk:
                details.append(getattr(self, 'keep_message', 'Matching copies in the opposite folder are kept.').strip())
        else:
            details.append('Relative subfolders are preserved. Existing files are never overwritten.')
            if policy == 'rename':
                details.append('Conflicting parent-folder names may also be renamed; see the destination paths below.')
            details.append('If a new conflict appears during the operation, '+('rename automatically.' if policy == 'rename' else 'ignore that file.'))
        details.extend(lines + skip_lines)
        confirmation = QMessageBox(self)
        confirmation.setWindowTitle(verb)
        confirmation.setText(message)
        confirmation.setTextFormat(Qt.TextFormat.PlainText)
        confirmation.setDetailedText('\n\n'.join(details))
        confirmation.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        confirmation.setDefaultButton(QMessageBox.StandardButton.No)
        if confirmation.exec() != QMessageBox.StandardButton.Yes:
            return
        self._transfer_cancel = threading.Event()
        self._operation_destination = destination_root
        self._created_merge_root = False
        self._operation_verb = verb
        self.progress.setRange(0, len(plan))
        self.progress.setValue(0)
        self.action_active = True
        self._transfer_running = True
        self.status.setText(verb+' in progress…')
        self._controls()
        previous_result = self.result
        roots = list(self.roots)
        recursive = self.recursive
        self._updated_result = None
        def perform(progress):
            snapshots = {}
            result, created = run_folder_action(
                operation, plan, policy, skipped, renamed, is_bulk,
                destination_root, roots, self._transfer_cancel, progress, snapshots)
            self._created_merge_root = created
            if not destination_root:
                self._updated_result = update_results(previous_result, operation, result[0], snapshots, roots, recursive)
            return result
        self.action_job = ActionJob(perform)
        self.action_job.signals.done.connect(self._acted)
        self.action_job.signals.progress.connect(self._action_progress)
        QThreadPool.globalInstance().start(self.action_job)

    def _action_progress(self, value, total):
        self.progress.setRange(0, total)
        self.progress.setValue(value)
        if self._transfer_cancel.is_set():
            self.status.setText('Stopping after the current file. Completed transfers will be kept.')
        else:
            self.status.setText(f'{self._operation_verb} · {value} of {total} files checked')

    def _acted(self, result, error):
        self.action_active = False
        self._transfer_running = False
        destination = getattr(self, '_operation_destination', None)
        self._operation_destination = None
        if error:
            self._show_operation_report('Operation failed', 'The operation could not be completed. See Show Details.', error, warning=True)
        elif result[1] and not (destination or result[2] or result[3]):
            self._show_operation_report('Operation finished with errors',
                                        f'{len(result[0])} file(s) processed · {len(result[1])} errors.\nSee Show Details for the affected files.',
                                        '\n\n'.join(result[1]), warning=True)
        if result and (destination or result[2] or result[3]):
            processed, errors, skipped, renamed = result
            details = ['PROCESSED\n'+'\n\n'.join(s+'\n  → '+d for s,d in processed),
                       'IGNORED\n'+'\n\n'.join(e['path']+'\n  → '+str(d)+'\n'+reason for e,d,reason in skipped if reason != STOPPED_REASON),
                       'NOT PROCESSED AFTER STOPPING\n'+'\n\n'.join(e['path']+'\n  → '+str(d or 'System Trash') for e,d,reason in skipped if reason == STOPPED_REASON),
                       'RENAMED\n'+'\n\n'.join(e['path']+'\n  → '+str(d) for e,_,d in renamed),
                       'ERRORS\n'+'\n'.join(errors)]
            stopped = sum(reason == STOPPED_REASON for _,_,reason in skipped)
            message = f'{len(processed)} processed · {len(skipped)-stopped} ignored · {stopped} not processed after stopping · {len(renamed)} renamed · {len(errors)} errors.'
            if stopped:
                message += '\nOperation stopped. Completed transfers were kept; unprocessed source files remain in place.'
            if destination:
                heading = 'Folder C: ' if self._created_merge_root else 'Folder C was not created. Requested location: '
                message = heading+str(destination)+'\n'+message+'\nA and B were left unchanged.'
            self._show_operation_report('Folder C result' if destination else 'Transfer result', message, '\n\n'.join(details), warning=bool(errors))
        if destination:
            stopped = bool(result and any(reason == STOPPED_REASON for _,_,reason in result[2]))
            failed = bool(error or (result and result[1]))
            self.status.setText('Folder C operation stopped.' if stopped else 'Folder C operation failed.' if failed else 'Folder C operation finished.')
            self._controls()
        else:
            updated = getattr(self, '_updated_result', None)
            if updated is not None:
                self.preview_cache.clear()
                self._scanned(updated, '', False)
            else:
                self.status.setText('Operation could not update the results. Scan again before continuing.')
                self.result = None
                for tree in self.trees.values():
                    tree.clear()
                self._selected()
                self._controls()
