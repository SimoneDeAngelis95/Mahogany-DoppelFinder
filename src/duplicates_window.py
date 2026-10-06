"""Search one folder for duplicate media, preserving a copy of each content group."""
from pathlib import Path
from PyQt6.QtCore import Qt, QThreadPool
from PyQt6.QtWidgets import QLabel, QMessageBox, QTreeWidgetItem
from folderfolder_window import folderfolder_window
from comparison_jobs import FolderScanJob


def deletion_entries(result, selected=None, media='all'):
    """A chosen batch must leave an unchanged copy in every affected group."""
    wanted = None if selected is None else {entry['path'] for entry in selected}
    entries = []
    for group in result['common']:
        copies = group['A']
        kind = 'images' if copies[0]['kind'] in ('image', 'animation') else copies[0]['kind']
        if media != 'all' and kind != media:
            continue
        removing = copies[1:] if wanted is None else [e for e in copies if e['path'] in wanted]
        keep = [e for e in copies if e not in removing]
        if removing and not keep:
            raise ValueError('Keep at least one file in each duplicate group. Nothing was changed.')
        # One explicit keeper suffices; it is checked before and during the batch.
        entries.extend(dict(e, keep_copies=keep[:1]) for e in removing)
    return entries


class duplicates_window(folderfolder_window):
    def __init__(self, folder, recursive=False, categories=None, parent=None, workers=0):
        self.folder = str(Path(folder).resolve())
        self.keep_message = '\nAt least one checked copy of each content group is kept in this folder.'
        super().__init__(self.folder, self.folder, recursive, categories, parent, workers)
        self.setWindowTitle('Find duplicates · Mahogany DoppelFinder')
        for key in ('only_b', 'uncertain'):
            self.tabs.removeTab(self.tabs.indexOf(self.trees[key]))
        self.copy.hide(); self.move.hide(); self.inspect.hide()
        self.bulk_buttons['B'].hide()
        self.bulk_buttons['A'].setText('Remove extra copies ▾')
        self.bulk_menu_actions[('A', 'copy')].setVisible(False)
        self.bulk_menu_actions[('A', 'move')].setVisible(False)
        for label in self.findChildren(QLabel):
            if label.text() == 'A  '+self.folder+'\nB  '+self.folder:
                label.setText('Folder  '+self.folder)
            elif label.text() in ('FILE A', 'FILE B'):
                label.setText('SELECTED COPY' if label.text() == 'FILE A' else 'ANOTHER COPY')
        self.trees['common'].setHeaderLabels(['Duplicate files', 'Details', 'Copies'])
        self.trees['only_a'].setHeaderLabels(['File', 'Details', ''])
        self.tabs.setTabText(self.tabs.indexOf(self.trees['only_a']), 'Non-duplicates')
        self.tabs.setTabToolTip(self.tabs.indexOf(self.trees['only_a']), 'Files with no verified duplicates found in this scan.')
        self._bulk_controls()

    def _scan(self):
        if self.busy or self.action_active: return
        self.busy = True; self.result = None; self.preview_cache.clear()
        self.hover_timer.stop(); self.hover_token += 1; self.hover_popup.hide()
        for tree in self.trees.values(): tree.clear()
        self._selected(); self.title.setText('Searching for duplicates…'); self.progress.setRange(0, 0)
        self._controls()
        self.scan_job = FolderScanJob((self.folder, None), self.recursive, set(self.categories), self.workers)
        self.scan_job.signals.progress.connect(self._progress)
        self.scan_job.signals.done.connect(self._scanned)
        self.scan_job.signals.activity.connect(self._worker_activity)
        self._start_scan_clock()
        QThreadPool.globalInstance().start(self.scan_job)

    def _scanned(self, result, error, cancelled):
        super()._scanned(result, error, cancelled)
        if result:
            extras = sum(len(g['A']) - 1 for g in result['common'])
            self.title.setText('Duplicate search complete')
            self.status.setText(f'{len(result["common"])} duplicate groups · {extras} extra copies · {len(result["only_a"])} files without verified duplicates · {len(result["notes"])} not compared' + self._scan_time_suffix())
            self.tabs.setTabText(self.tabs.indexOf(self.trees['common']), f'Duplicates ({len(result["common"])})')
            self.tabs.setTabText(self.tabs.indexOf(self.trees['only_a']), f'Non-duplicates ({len(result["only_a"])})')
            self.tabs.setTabText(self.tabs.indexOf(self.trees['notes']), f'Not compared ({len(result["notes"])})')
            self._refresh_result_view()

    def _populate(self):
        super()._populate()
        tree = self.trees['common']
        for index in range(tree.topLevelItemCount()):
            item = tree.topLevelItem(index)
            item.setText(0, f'Duplicate group {index + 1}')
            item.setText(2, f'{item.childCount()} copies')
            for child_index in range(item.childCount()):
                item.child(child_index).setText(2, '')

        singles = self.trees['only_a']
        singles.clear()
        for group in self.result['only_a']:
            for entry in group['A']:
                relative = str(Path(entry['path']).relative_to(self.folder))
                item = QTreeWidgetItem([relative, f'{entry["signature"][2]:,} bytes · {entry["kind"]}', ''])
                item.setToolTip(0, entry['path'])
                item.setData(0, Qt.ItemDataRole.UserRole, {'entry': entry})
                singles.addTopLevelItem(item)
        self._selected()

    def _controls(self):
        super()._controls()
        if self.tabs.currentWidget() is self.trees['only_a']:
            self.trash.setEnabled(False)

    def _selected(self):
        tree = self.tabs.currentWidget(); items = tree.selectedItems() if tree else []
        data = (items[0].data(0, Qt.ItemDataRole.UserRole) or {}) if items else {}
        copies = [e for e in data.get('group', {}).get('A', []) if self._entry_visible(e)]
        entry = data.get('entry') or (copies[0] if copies else None)
        other = next((e for e in copies if entry and e['path'] != entry['path']), None)
        self._show_preview(0, entry); self._show_preview(1, other)
        self._controls()

    def _bulk_controls(self):
        if not hasattr(self, 'bulk_menu_actions'): return
        ready = bool(self.result) and not self.busy and not self.action_active
        self.bulk_media.setEnabled(ready)
        entries = deletion_entries(self.result, media=self.bulk_media.currentData()) if self.result else []
        self.bulk_menu_actions[('A', 'trash')].setText(f'Move extra copies to Trash ({len(entries)})')
        self.bulk_menu_actions[('A', 'trash')].setEnabled(ready and bool(entries))
        self.bulk_buttons['A'].setEnabled(ready and bool(entries))
        self.bulk_buttons['B'].setEnabled(False)
        self.bulk_hint.setText('Keeps the first file, sorted by path, in each duplicate group. Select individual files to choose which copies to remove instead.')

    def _bulk_action(self, side, operation, scope):
        if operation == 'trash': self._action('trash', deletion_entries(self.result, media=self.bulk_media.currentData()), 'Remove extra copies')

    def _action(self, operation, entries=None, scope_label=None):
        if operation != 'trash' or self.busy or self.action_active or not self.result: return
        if entries is None:
            items = self.tabs.currentWidget().selectedItems()
            if not items or any('entry' not in (item.data(0, Qt.ItemDataRole.UserRole) or {}) for item in items):
                QMessageBox.information(self, 'Select individual files', 'Select the file rows you want to remove.'); return
            selected = self._selection()
            if selected and all(e.get('not_compared') for e in selected):
                super()._action('trash', selected, 'Selected files not compared')
                return
            try: entries = deletion_entries(self.result, self._selection())
            except ValueError as error:
                QMessageBox.warning(self, 'Keep a copy', str(error)); return
        keep = sorted({copy['path'] for e in entries for copy in e['keep_copies']})
        label = (scope_label or 'Selected duplicate files')+'\n\nFiles kept:\n'+'\n'.join(keep)
        super()._action(operation, entries, label)

    def _inspect(self):
        return
