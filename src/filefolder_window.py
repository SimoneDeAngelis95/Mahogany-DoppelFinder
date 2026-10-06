"""File/folder result dialog, sharing previews and actions with folder/folder."""
from pathlib import Path
import os
from PyQt6.QtCore import QFile, QThreadPool, Qt, pyqtSignal
from PyQt6.QtWidgets import QLabel, QMenu, QMessageBox, QPushButton, QTreeWidgetItem

from filefile_window import _Job, file_signature, filefile_window, move_without_overwrite
from folderfolder_window import folderfolder_window
from folder_operations import not_compared_entry
from comparison_results import update_reference
from comparison_jobs import FolderScanJob
from file_transfers import copy_without_overwrite
from filefolder_scan import scan_file_folder
from folder_scan import ScanCancelled


class _FileFolderJob(FolderScanJob):
    def __init__(self, reference, folder, file_side, recursive, categories, workers=0):
        super().__init__((reference, folder), recursive, categories, workers)
        self.file_side = file_side

    def run(self):
        try:
            result = scan_file_folder(*self.roots, self.file_side, self.recursive,
                                      self.categories, self.cancel, self.signals.progress.emit, self.workers, self.signals.activity.emit)
            self.signals.done.emit(result, '', False)
        except ScanCancelled:
            self.signals.done.emit(None, '', True)
        except Exception as error:
            self.signals.done.emit(None, str(error), False)


class filefolder_window(folderfolder_window):
    referenceChanged = pyqtSignal(str)

    def __init__(self, reference, folder, file_side='A', recursive=False, categories=None, parent=None, workers=0):
        self.reference = os.path.abspath(os.fspath(reference))
        self.folder = str(Path(folder).resolve())
        self.file_side = file_side
        self.folder_side = 'B' if file_side == 'A' else 'A'
        roots = [str(Path(self.reference).parent), self.folder]
        if file_side == 'B': roots.reverse()
        super().__init__(*roots, recursive, categories, parent, workers)
        self.setWindowTitle('Find file in folder · Mahogany DoppelFinder')
        # Keep only the result views that apply to one reference file.
        for key in ('only_a' if self.folder_side == 'B' else 'only_b', 'uncertain'):
            self.tabs.removeTab(self.tabs.indexOf(self.trees[key]))
        self.result_keys = ['common', 'only_a' if self.folder_side=='A' else 'only_b', 'notes']
        for index, label in enumerate(('Matches', 'Different files', 'Not compared')):
            self.tabs.setTabText(index, label)
        for tree in self.trees.values():
            tree.setHeaderLabels(['File in folder', 'Details', 'Side'])
        self.layout().itemAt(1).widget().setText(f'Reference {self.file_side}  {self.reference}\nFolder {self.folder_side}  {self.folder}')
        reference_panel = self.panels['AB'.index(self.file_side)]
        reference_panel['name'].parentWidget().layout().itemAt(0).widget().setText('REFERENCE FILE '+self.file_side)
        self.panels['AB'.index(self.folder_side)]['name'].parentWidget().layout().itemAt(0).widget().setText('FOLDER '+self.folder_side+' · SELECTED FILE')
        reference_actions = QPushButton('Reference file actions ▾')
        reference_menu = QMenu(reference_actions)
        self.reference_buttons = [reference_actions]
        for text, operation in [('Copy reference into folder', 'copy'), ('Move reference into folder', 'move'), ('Move reference to Trash', 'trash')]:
            action = reference_menu.addAction(text)
            action.triggered.connect(lambda checked=False, op=operation: self._reference_action(op))
            self.reference_buttons.append(action)
        reference_actions.setMenu(reference_menu)
        reference_panel['name'].parentWidget().layout().addWidget(reference_actions)
        self.copy.setText('Copy selected to reference folder')
        self.move.setText('Move selected to reference folder')
        self._controls()

    def _scan(self):
        if self.busy or self.action_active: return
        self.busy = True; self.result = None; self.preview_cache.clear()
        self.hover_timer.stop(); self.hover_token += 1; self.hover_popup.hide()
        for tree in self.trees.values(): tree.clear()
        self._selected(); self.title.setText('Looking for matching content…'); self.progress.setRange(0, 0)
        self._controls()
        if not self.reference:
            self._scanned(None, 'Choose a new reference file in the main window to continue.', False)
            self.title.setText('Reference file moved to Trash')
            return
        self.scan_job = _FileFolderJob(self.reference, self.folder, self.file_side, self.recursive, set(self.categories), self.workers)
        self.scan_job.signals.progress.connect(self._progress); self.scan_job.signals.done.connect(self._scanned)
        self.scan_job.signals.activity.connect(self._worker_activity)
        self._start_scan_clock()
        QThreadPool.globalInstance().start(self.scan_job)

    def _scanned(self, result, error, cancelled):
        super()._scanned(result, error, cancelled)
        if result:
            self.title.setText('Matching content found' if result['matches'] else 'No matching content found')
            self.status.setText(f'{len(result["matches"])} matches · {len(result["different"])} different files · {len(result["notes"])} not compared' + self._scan_time_suffix())
            self._refresh_result_view()

    def _populate(self):
        # The reference is displayed in its fixed pane, never as a selectable result row.
        keys = ['common', 'only_a' if self.folder_side=='A' else 'only_b', 'notes']
        names = ['Matches', 'Different files', 'Not compared']
        for index, key in enumerate(keys):
            tree = self.trees[key]; tree.clear()
            values = self.result['matches'] if key=='common' else self.result['different'] if key!='notes' else self.result['notes']
            tab = self.tabs.indexOf(tree)
            if tab >= 0: self.tabs.setTabText(tab, f'{names[index]} ({len(values)})')
            for entry in values:
                relative = str(Path(entry['path']).relative_to(self.folder))
                if key == 'notes':
                    item = QTreeWidgetItem([relative, entry['reason'], entry['side']])
                    item.setData(0, Qt.ItemDataRole.UserRole, {'note': entry})
                    note_entry = not_compared_entry(entry)
                    if note_entry:
                        item.setData(0, Qt.ItemDataRole.UserRole, {'entry': note_entry})
                else:
                    item = QTreeWidgetItem([relative, f'{entry["signature"][2]:,} bytes · {entry["kind"]}', entry['side']])
                    group = {'A': [], 'B': []}; group[self.file_side] = [self.result['reference']]; group[self.folder_side] = [entry]
                    item.setData(0, Qt.ItemDataRole.UserRole, dict(entry=entry, group=group))
                item.setToolTip(0, entry['path']); tree.addTopLevelItem(item)
            tree.setColumnWidth(0, 510); tree.setColumnWidth(1, 300)
        self.tabs.setCurrentWidget(self.trees['common'])
        if self.trees['common'].topLevelItemCount():
            self.trees['common'].setCurrentItem(self.trees['common'].topLevelItem(0))
        self._selected()

    def _selection(self):
        entries = super()._selection()
        matches = {entry['path'] for entry in self.result['matches']} if self.result else set()
        return [dict(entry, keep_copies=[self.result['reference']]) if entry['path'] in matches else entry for entry in entries]

    def _selected(self):
        if not hasattr(self, 'panels'): return
        tree = self.tabs.currentWidget(); selected = tree.selectedItems() if tree else []
        entry = (selected[0].data(0, Qt.ItemDataRole.UserRole) or {}).get('entry') if selected else None
        reference = self.result['reference'] if self.result else None
        self._show_preview('AB'.index(self.file_side), reference)
        self._show_preview('AB'.index(self.folder_side), entry)
        self._controls()

    def _bulk_controls(self):
        if not hasattr(self, 'bulk_menu_actions'): return
        ready = bool(self.result) and not self.busy and not self.action_active
        self.bulk_media.hide(); self.bulk_buttons[self.file_side].hide()
        for label in self.bulk_hint.parentWidget().findChildren(QLabel):
            if label.text() == 'Whole-folder actions': label.setText('Matching copies in the folder')
        count = len(self._matching_entries())
        self.bulk_buttons[self.folder_side].setText('All matching copies ▾')
        self.bulk_buttons[self.folder_side].setEnabled(ready and count > 0)
        for operation, text in [('trash', 'Move all matches to Trash'), ('move', 'Move all matches to reference folder'), ('copy', 'Copy all matches to reference folder')]:
            action = self.bulk_menu_actions[(self.folder_side, operation)]
            action.setText(f'{text} ({count})'); action.setEnabled(ready and count > 0)
        self.bulk_hint.setText('The reference file is kept. Existing destination names are never overwritten.' if ready else 'Available after a complete scan.')

    def _matching_entries(self):
        if not self.result: return []
        return [dict(entry, keep_copies=[self.result['reference']]) for entry in self.result['matches']]

    def _bulk_action(self, side, operation, scope):
        if side != self.folder_side or self.busy or self.action_active: return
        self._action(operation, self._matching_entries(), 'All matching copies in folder '+self.folder_side)

    def _controls(self):
        super()._controls()
        if hasattr(self, 'reference_buttons'):
            for button in self.reference_buttons: button.setEnabled(bool(self.result) and not self.busy and not self.action_active)

    def _inspect(self):
        entries = [p['entry'] for p in self.panels]
        if not all(entries): return
        self.inspect_window = filefile_window(entries[0]['path'], entries[1]['path'], self)
        self._inspection_paths = [e['path'] for e in entries]
        self.inspect_window.pathsChanged.connect(self._pair_changed)
        self.inspect_window.show()

    def _pair_changed(self, path_a, path_b):
        if not self.result:
            self._inspection_paths = [path_a, path_b]
            return
        reference = (path_a, path_b)['AB'.index(self.file_side)]
        if reference == self.reference:
            super()._pair_changed(path_a, path_b)
            return
        self.reference = reference
        if reference: self.roots['AB'.index(self.file_side)] = str(Path(reference).parent)
        self.referenceChanged.emit(reference)
        self._inspection_paths = [path_a, path_b]
        self.layout().itemAt(1).widget().setText(f'Reference {self.file_side}  {self.reference or "Moved to Trash"}\nFolder {self.folder_side}  {self.folder}')
        self.preview_cache.clear()
        try:
            signature = file_signature(reference) if reference else None
            if signature and signature[2:4] != self.result['reference']['signature'][2:4]:
                signature = None
        except OSError:
            signature = None
        if signature is None:
            self.result = None
            for tree in self.trees.values(): tree.clear()
            self._selected()
            self.status.setText('Reference file unavailable. Choose another file in the main window.')
            self._controls()
        else:
            self._scanned(update_reference(self.result, 'move', reference, signature), '', False)

    def _reference_action(self, operation):
        if self.busy or self.action_active or not self.result: return
        entry = self.result['reference']; source = Path(entry['path']); destination = Path(self.folder)/source.name
        try:
            if source.is_symlink() or file_signature(source) != entry['signature']: raise ValueError('Reference changed. Scan again.')
            if operation != 'trash' and destination.exists(): raise ValueError('The destination name already exists. Nothing was changed.')
        except (OSError, ValueError) as error:
            QMessageBox.warning(self, 'Reference action unavailable', str(error)); return
        text = f'{operation.title()} the reference file?\n\n{source}'
        if operation!='trash': text += '\n→ '+str(destination)
        else: text += '\n\nThis moves the reference itself to the system Trash.'
        if QMessageBox.question(self, 'Reference file', text, QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes: return
        self._reference_operation = operation
        self._reference_destination = str(destination)
        self._reference_snapshot = None
        self.action_active = True; self._controls()
        def perform():
            if file_signature(source) != entry['signature']: raise ValueError('Reference changed. Scan again.')
            if operation=='trash':
                file=QFile(str(source))
                if not file.moveToTrash(): raise OSError(file.errorString() or 'System Trash unavailable')
                return ''
            if operation=='copy':
                copy_without_overwrite(source,destination,entry['signature'])
                value = str(source)
            else:
                value = move_without_overwrite(source,destination,entry['signature'])
            try:
                signature = file_signature(destination)
                self._reference_snapshot = signature if signature[2:4] == entry['signature'][2:4] else None
            except OSError:
                pass
            return value
        self.action_job = _Job(perform); self.action_job.signals.done.connect(self._reference_done)
        QThreadPool.globalInstance().start(self.action_job)

    def _reference_done(self, path, error):
        self.action_active = False
        if error:
            QMessageBox.warning(self, 'Reference action failed', error)
            self.status.setText('Reference action failed. Scan again if files changed.')
            self._controls()
            return
        operation = self._reference_operation
        if path != self.reference:
            self.reference = path
            if path: self.roots['AB'.index(self.file_side)] = str(Path(path).parent)
            self.referenceChanged.emit(path)
        self.layout().itemAt(1).widget().setText(f'Reference {self.file_side}  {self.reference or "Moved to Trash"}\nFolder {self.folder_side}  {self.folder}')
        self.preview_cache.clear()
        if not path or (operation == 'move' and self._reference_snapshot is None):
            self.result = None
            for tree in self.trees.values(): tree.clear()
            self._selected()
            self.title.setText('Reference file unavailable')
            self.status.setText('Choose a reference file in the main window to compare again.')
            self._controls()
        else:
            updated = update_reference(self.result, operation, self._reference_destination, self._reference_snapshot)
            self._scanned(updated, '', False)
