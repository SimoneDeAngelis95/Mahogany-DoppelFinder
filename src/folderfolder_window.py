"""Folder comparison dialog: result trees, selection and interface layout."""
from pathlib import Path
import stat
import time

from PyQt6.QtCore import QItemSelectionModel, QEvent, QThreadPool, QTimer, QUrl, Qt
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import (QDialog, QFrame, QHBoxLayout, QLabel,
                            QProgressBar, QPushButton, QSplitter, QTabWidget,
                            QTreeWidget, QTreeWidgetItem, QVBoxLayout,
                            QAbstractItemView, QComboBox, QMenu, QCheckBox, QSizePolicy, QMessageBox)

from dialog_position import configure_result_window, place_result_window
from comparison_jobs import FolderScanJob
from comparison_previews import ComparisonPreviews
from folder_operations import FolderOperations, not_compared_entry
from filefile_window import filefile_window, file_signature
import quick_look
from folder_actions import merged_entries
from comparison_results import update_results

class WorkerFileLabel(QLabel):
    """A single-line path that elides as the result window is resized."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.full_text = ''
        self.setTextFormat(Qt.TextFormat.PlainText)
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)

    def set_file(self, slot, display_path='', full_path=''):
        self.full_text = f'Thread {slot} · {display_path or "Idle"}'
        self.setToolTip(full_path)
        self._fit_text()

    def _fit_text(self):
        self.setText(self.fontMetrics().elidedText(self.full_text, Qt.TextElideMode.ElideMiddle,
                                                 max(0, self.contentsRect().width())))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._fit_text()


class folderfolder_window(ComparisonPreviews, FolderOperations, QDialog):
    """Build the result interface and coordinate scans and tree selection."""
    def showEvent(self, event):
        super().showEvent(event)
        if not getattr(self, '_initial_position_set', False):
            self._initial_position_set = True
            QTimer.singleShot(0, lambda: place_result_window(self, large=True))

    def __init__(self, path_a, path_b, recursive=False, categories=None, parent=None, workers=0):
        super().__init__(parent)
        self.roots = [str(Path(p).resolve()) for p in (path_a, path_b)]
        self.recursive = recursive
        self.workers = workers
        self.categories = set(categories if categories is not None else ('images', 'audio', 'video'))
        self.busy = False
        self.action_active = False
        self.result = None
        self._initialize_previews()
        self.setWindowTitle('Folder comparison · Mahogany DoppelFinder')
        configure_result_window(self)
        self.resize(1100, 790)
        self.setStyleSheet('''
            QDialog { background: #f4f7fb; color: #27364a; }
            QLabel { color: #27364a; }
            QFrame#previewCard { background: white; border: 1px solid #dce3ec; border-radius: 12px; }
            QPushButton { background: white; padding: 8px 10px; border: 1px solid #cfd8e3; border-radius: 7px; color: #27364a; }
            QPushButton:hover { background: #eaf3f7; }
            QPushButton::menu-indicator { image: none; width: 0px; height: 0px; }
            QPushButton:disabled { color: #9aa6b5; }
            QTreeWidget { background: white; border: 1px solid #dce3ec; border-radius: 8px; }
            QTreeWidget::item { padding: 6px; }
            QTreeWidget::item:selected { background: #dceff5; color: #1f3441; }
        ''')
        main = QVBoxLayout(self)
        main.setContentsMargins(16, 16, 16, 14)
        main.setSpacing(8)
        self._build_header(main)
        self._build_results(main)
        self._build_actions(main)
        self._build_footer(main)
        self._controls()
        self._scan()

    def _build_header(self, main):
        self.title = QLabel('Compare folder contents')
        self.title.setStyleSheet('font-size: 22px; font-weight: 600;')
        main.addWidget(self.title)
        paths = QLabel('A  '+self.roots[0]+'\nB  '+self.roots[1])
        paths.setTextFormat(Qt.TextFormat.PlainText)
        paths.setWordWrap(True)
        paths.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        main.addWidget(paths)
        self.status = QLabel()
        self.status.setWordWrap(True)
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        main.addWidget(self.status)
        progress_row = QHBoxLayout()
        self.progress = QProgressBar()
        self.show_hidden = QCheckBox('Show hidden files')
        self.show_hidden.setToolTip('Show hidden files and files inside hidden subfolders. This only changes the displayed results; whole-folder actions and C still use the completed scan.')
        self.show_hidden.toggled.connect(self._refresh_result_view)
        progress_row.addWidget(self.show_hidden)
        progress_row.addWidget(self.progress, 1)
        self.scan_time = QLabel('Scan time: 0.0 s')
        progress_row.addWidget(self.scan_time)
        self.scan_clock = QTimer(self)
        self.scan_clock.setInterval(250)
        self.scan_clock.timeout.connect(self._update_scan_clock)
        self.stop = QPushButton('Stop scan')
        self.stop.clicked.connect(self._stop)
        progress_row.addWidget(self.stop)
        main.addLayout(progress_row)
        self.worker_panel = QFrame()
        self.worker_panel.setStyleSheet('QFrame { background: #eaf0f6; border-radius: 7px; }')
        worker_layout = QVBoxLayout(self.worker_panel)
        worker_layout.setContentsMargins(10, 6, 10, 6)
        worker_layout.setSpacing(2)
        heading = QLabel('Files being processed')
        heading.setStyleSheet('font-weight: 600;')
        worker_layout.addWidget(heading)
        self.worker_labels = []
        for slot in range(1, 5):
            label = WorkerFileLabel()
            label.set_file(slot)
            label.hide()
            worker_layout.addWidget(label)
            self.worker_labels.append(label)
        self.worker_panel.hide()
        main.addWidget(self.worker_panel)

    def _build_results(self, main):
        tools = QHBoxLayout()
        self.selection_count = QLabel('No files selected')
        self.expand_all = QPushButton('Expand all')
        self.collapse_all = QPushButton('Collapse all')
        for button, expand in ((self.expand_all, True), (self.collapse_all, False)):
            button.setStyleSheet('QPushButton { padding: 4px 8px; }')
            button.clicked.connect(lambda checked=False, value=expand: self._set_groups_expanded(value))
            tools.addWidget(button)
        tools.addStretch()
        tools.addWidget(self.selection_count)
        main.addLayout(tools)
        self.uncertainty_notice = QFrame()
        notice_row = QHBoxLayout(self.uncertainty_notice)
        notice_row.setContentsMargins(8, 4, 8, 4)
        self.uncertainty_text = QLabel()
        self.uncertainty_text.setTextFormat(Qt.TextFormat.PlainText)
        self.uncertainty_text.setWordWrap(True)
        notice_row.addWidget(self.uncertainty_text, 1)
        self.uncertainty_details = QPushButton('Why these results?')
        self.uncertainty_details.clicked.connect(self._show_uncertainty_details)
        notice_row.addWidget(self.uncertainty_details)
        self.uncertainty_notice.hide()
        main.addWidget(self.uncertainty_notice)
        self.splitter = QSplitter(Qt.Orientation.Vertical)
        self.tabs = QTabWidget()
        self.tabs.setMinimumHeight(240)
        self.trees = {}
        for key, name in [('common', 'In common'), ('only_a', 'Only in A'), ('only_b', 'Only in B'), ('uncertain', 'Needs checking'), ('notes', 'Not compared')]:
            tree = QTreeWidget()
            tree.setColumnCount(3)
            tree.setHeaderLabels(['File', 'Reason', ''] if key == 'notes' else ['File A', 'File B', 'Copies'])
            tree.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
            tree.setMouseTracking(True)
            tree.viewport().installEventFilter(self)
            if quick_look.available():
                tree.installEventFilter(self)
                tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
                tree.customContextMenuRequested.connect(lambda point, t=tree: self._quick_look_menu(t, point))
            tree.itemSelectionChanged.connect(self._selected)
            tree.itemEntered.connect(self._hover)
            tree.itemDoubleClicked.connect(self._double_clicked)
            self.trees[key] = tree
            self.tabs.addTab(tree, name)
        self.tabs.currentChanged.connect(self._selected)
        self.splitter.addWidget(self.tabs)
        panel = self._build_preview_panels()
        self.splitter.addWidget(panel)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setHandleWidth(8)
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 0)
        self.splitter.setSizes([480, 210])
        main.addWidget(self.splitter, 1)

    def _build_actions(self, main):
        actions = QHBoxLayout()
        self.copy = QPushButton('Copy to other folder')
        self.move = QPushButton('Move to other folder')
        self.trash = QPushButton('Move to Trash')
        self.trash.setStyleSheet('QPushButton { color: #a34040; } QPushButton:disabled { color: #9aa6b5; }')
        for button, operation in [(self.copy, 'copy'), (self.move, 'move'), (self.trash, 'trash')]:
            button.clicked.connect(lambda checked=False, op=operation: self._action(op))
            actions.addWidget(button)
        self.inspect = QPushButton('Compare displayed A / B')
        self.inspect.clicked.connect(self._inspect)
        actions.addWidget(self.inspect)
        main.addLayout(actions)
        bulk = QFrame()
        bulk.setObjectName('bulkActions')
        bulk.setStyleSheet('QFrame#bulkActions { background: #eaf0f5; border-radius: 10px; }')
        bulk_layout = QVBoxLayout(bulk)
        bulk_row = QHBoxLayout()
        bulk_row.addWidget(QLabel('Whole-folder actions'))
        self.bulk_media = QComboBox()
        for label, category in [('All scanned media', 'all'), ('Photos & images', 'images'), ('Audio', 'audio'), ('Videos', 'video')]:
            self.bulk_media.addItem(label, category)
        self.bulk_media.currentIndexChanged.connect(self._bulk_controls)
        bulk_row.addWidget(self.bulk_media)
        bulk_row.addStretch()
        self.bulk_buttons = {}
        self.bulk_menu_actions = {}
        for side, color in [('A', '#276675'), ('B', '#52677f')]:
            button = QPushButton('Folder '+side+' actions ▾')
            button.setStyleSheet('color: '+color+'; font-weight: 600;')
            menu = QMenu(button)
            for operation, scope in [('trash', 'matching'), ('move', 'unique'), ('copy', 'unique')]:
                action = menu.addAction('')
                action.triggered.connect(lambda checked=False, s=side, op=operation, sc=scope: self._bulk_action(s, op, sc))
                self.bulk_menu_actions[(side, operation)] = action
            button.setMenu(menu)
            self.bulk_buttons[side] = button
            bulk_row.addWidget(button)
        self.merge_button = QPushButton('Create folder C')
        self.merge_button.setToolTip('Create C from all verified scanned media, independently of the A/B media filter. Choose A or B for shared content; internal copies and subfolders are preserved.')
        self.merge_button.clicked.connect(self._create_merged_folder)
        self.merge_button.setVisible(type(self) is folderfolder_window)
        bulk_row.addSpacing(12)
        bulk_row.addWidget(self.merge_button)
        bulk_layout.addLayout(bulk_row)
        self.bulk_hint = QLabel()
        self.bulk_hint.setWordWrap(True)
        self.bulk_hint.setStyleSheet('color: #64748b; font-size: 12px;')
        bulk_layout.addWidget(self.bulk_hint)
        main.addWidget(bulk)

    def _build_footer(self, main):
        footer = QHBoxLayout()
        self.rescan = QPushButton('Scan again')
        self.rescan.clicked.connect(self._scan)
        footer.addWidget(self.rescan)
        footer.addStretch()
        self.close_button = QPushButton('Close')
        self.close_button.clicked.connect(self.close)
        footer.addWidget(self.close_button)
        main.addLayout(footer)

    def _scan(self):
        if self.busy or self.action_active:
            return
        self.busy = True
        self.result = None
        self.preview_cache.clear()
        self.hover_timer.stop()
        self.hover_token += 1
        self.hover_popup.hide()
        for tree in self.trees.values():
            tree.clear()
        self._selected()
        self.title.setText('Scanning folder contents…')
        self.progress.setRange(0, 0)
        self._controls()
        self.scan_job = FolderScanJob(tuple(self.roots), self.recursive, set(self.categories), self.workers)
        self.scan_job.signals.progress.connect(self._progress)
        self.scan_job.signals.done.connect(self._scanned)
        self.scan_job.signals.activity.connect(self._worker_activity)
        self._start_scan_clock()
        QThreadPool.globalInstance().start(self.scan_job)

    def _worker_activity(self, slot, side, path):
        if not self.busy or not 1 <= slot <= len(self.worker_labels):
            return
        label = self.worker_labels[slot - 1]
        display = ''
        if path:
            try:
                display = str(Path(path).relative_to(self.roots['AB'.index(side)]))
            except (ValueError, IndexError):
                display = Path(path).name
            display = f'{side}/{display}'
        label.set_file(slot, display, path)
        label.show()
        self.worker_panel.show()

    def _progress(self, value, total, text):
        if self.scan_job.cancel.is_set():
            return
        self.progress.setRange(0, total if total else 0)
        self.progress.setValue(value)
        self.status.setText(text)

    def _stop(self):
        if getattr(self, '_transfer_running', False):
            self._transfer_cancel.set()
            self.stop.setEnabled(False)
            self.status.setText('Stopping after the current file. Completed transfers will be kept.')
            return
        self.scan_job.cancel.set()
        self.stop.setEnabled(False)
        self.status.setText('Stopping after the current media check…')

    def _scanned(self, result, error, cancelled):
        self.scan_clock.stop()
        started = getattr(self, '_scan_started_at', None)
        if started is not None:
            self._scan_elapsed = time.perf_counter() - started
        self._scan_started_at = None
        self.busy = False
        self.progress.setRange(0, 1)
        self.progress.setValue(1 if result else 0)
        if cancelled:
            self.title.setText('Scan stopped')
            self.status.setText('No incomplete results are shown. Scan again when ready.')
        elif error:
            self.title.setText('Scan could not be completed')
            self.status.setText(error)
        else:
            self.result = result
            self.title.setText('Folder comparison complete')
            self.status.setText(f'{len(result["common"])} content groups in common · {len(result["only_a"])} only in A · {len(result["only_b"])} only in B · {len(result["uncertain"])} need checking · {len(result["notes"])} not compared' + self._scan_time_suffix())
            self._populate()
            self._refresh_result_view()
        self._controls()

    def _start_scan_clock(self):
        self.worker_panel.hide()
        for slot, label in enumerate(self.worker_labels, 1):
            label.set_file(slot)
            label.hide()
        self._scan_started_at = time.perf_counter()
        self._scan_elapsed = None
        self._update_scan_clock()
        self.scan_clock.start()

    def _update_scan_clock(self):
        started = getattr(self, '_scan_started_at', None)
        if started is not None:
            elapsed = time.perf_counter() - started
            self.scan_time.setText(self._scan_time_suffix(elapsed).removeprefix(' · '))

    def _scan_time_suffix(self, elapsed=None):
        """Format elapsed wall time consistently for all folder comparison modes."""
        if elapsed is None:
            elapsed = getattr(self, '_scan_elapsed', None)
        if elapsed is None:
            return ''
        seconds = round(max(0, elapsed), 1)
        if seconds < 60:
            duration = f'{seconds:.1f} s'
        else:
            minutes, seconds = divmod(round(seconds), 60)
            hours, minutes = divmod(minutes, 60)
            duration = f'{minutes} min {seconds:02d} s'
            if hours:
                duration = f'{hours} h {minutes:02d} min {seconds:02d} s'
        return ' · Scan time: ' + duration

    def _entry_visible(self, entry):
        if self.show_hidden.isChecked():
            return True
        path = Path(entry['path'])
        root = Path(self.roots['AB'.index(entry['side'])])
        try:
            relative = path.relative_to(root)
        except ValueError:
            relative = Path(path.name)
        for component in relative.parts:
            if component.startswith('.'):
                return False
        current = path
        while current != root and current != current.parent:
            try:
                info = current.lstat()
                if getattr(info, 'st_flags', 0) & getattr(stat, 'UF_HIDDEN', 0):
                    return False
                if getattr(info, 'st_file_attributes', 0) & getattr(stat, 'FILE_ATTRIBUTE_HIDDEN', 0):
                    return False
            except OSError:
                pass
            current = current.parent
        return True

    def _apply_hidden_filter(self):
        """Filter existing tree rows; the completed scan and batch plans stay intact."""
        for key, tree in self.trees.items():
            signals_blocked = tree.blockSignals(True)
            count = 0
            for index in range(tree.topLevelItemCount()):
                item = tree.topLevelItem(index)
                if item.childCount():
                    visible = []
                    for number in range(item.childCount()):
                        child = item.child(number)
                        entry = (child.data(0, Qt.ItemDataRole.UserRole) or {}).get('entry')
                        shown = bool(entry) and self._entry_visible(entry)
                        child.setHidden(not shown)
                        if shown:
                            visible.append(entry)
                        else:
                            child.setSelected(False)
                    item.setHidden(not visible)
                    if not visible:
                        item.setSelected(False)
                    if key == 'common' and len(set(self.roots)) == 1:
                        item.setText(2, f'{len(visible)} visible copies')
                    else:
                        item.setText(2, f'{sum(e["side"] == "A" for e in visible)} A · {sum(e["side"] == "B" for e in visible)} B')
                else:
                    data = item.data(0, Qt.ItemDataRole.UserRole) or {}
                    entry = data.get('entry') or data.get('note')
                    shown = not entry or self._entry_visible(entry)
                    item.setHidden(not shown)
                    if not shown:
                        item.setSelected(False)
                count += not item.isHidden()
            tree.blockSignals(signals_blocked)
            tab = self.tabs.indexOf(tree)
            if tab >= 0:
                label = self.tabs.tabText(tab).rsplit(' (', 1)[0]
                self.tabs.setTabText(tab, f'{label} ({count})')
        self._selected()

    def _refresh_result_view(self):
        if not self.result:
            return
        self.hover_timer.stop()
        self.hover_token += 1
        self.hover_popup.hide()
        self._apply_hidden_filter()

    def _populate(self):
        names = ['In common', 'Only in A', 'Only in B', 'Needs checking', 'Not compared']
        for index, (key, tree) in enumerate(self.trees.items()):
            tree.clear()
            self.tabs.setTabText(index, f'{names[index]} ({len(self.result[key])})')
            if key == 'notes':
                for note in self.result[key]:
                    item = QTreeWidgetItem([note['side']+' · '+Path(note['path']).name, note['reason'], ''])
                    item.setData(0, Qt.ItemDataRole.UserRole, {'note': note})
                    entry = not_compared_entry(note)
                    if entry:
                        item.setData(0, Qt.ItemDataRole.UserRole, {'entry': entry})
                    item.setToolTip(0, note['path'])
                    tree.addTopLevelItem(item)
            else:
                for number, group in enumerate(self.result[key], 1):
                    title = ('Matching content' if key=='common' else 'Unverified content' if key=='uncertain' else 'Content group')+f' {number}'
                    parent = QTreeWidgetItem([title, '', f'{len(group["A"])} A · {len(group["B"])} B'])
                    if key == 'uncertain':
                        causes = self._uncertainty_causes(group)
                        summary = self._uncertainty_summary(causes)
                        parent.setToolTip(0, summary)
                        parent.setToolTip(1, summary)
                    parent.setData(0, Qt.ItemDataRole.UserRole, {'group': group})
                    tree.addTopLevelItem(parent)
                    for side in ('A', 'B'):
                        for entry in group[side]:
                            relative = str(Path(entry['path']).relative_to(self.roots['AB'.index(side)]))
                            child = QTreeWidgetItem([relative if side=='A' else '', relative if side=='B' else '', side])
                            child.setData(0, Qt.ItemDataRole.UserRole, {'entry': entry, 'group': group})
                            parent.addChild(child)
                    parent.setExpanded(number <= 3)
            tree.setColumnWidth(0, 370)
            tree.setColumnWidth(1, 370)
        if self.trees['common'].topLevelItemCount():
            self.trees['common'].setCurrentItem(self.trees['common'].topLevelItem(0))
        self._selected()

    def _selection(self):
        tree = self.tabs.currentWidget()
        entries = {}
        if tree is None:
            return []
        for item in tree.selectedItems():
            if item.isHidden():
                continue
            data = item.data(0, Qt.ItemDataRole.UserRole) or {}
            if 'entry' in data:
                values = [data['entry']]
            elif 'group' in data:
                values = data['group']['A'] + data['group']['B']
            else:
                values = []
            for entry in values:
                if not self._entry_visible(entry):
                    continue
                entries[(entry['side'], entry['path'])] = entry
        return list(entries.values())

    def _selected(self):
        tree = self.tabs.currentWidget()
        selected = tree.selectedItems() if tree else []
        data = (selected[0].data(0, Qt.ItemDataRole.UserRole) or {}) if selected else {}
        group = data.get('group', {'A': [], 'B': []})
        for index, side in enumerate(('A', 'B')):
            entry = data.get('entry')
            if not entry or entry['side'] != side:
                entry = next((e for e in group[side] if self._entry_visible(e)), None)
            self._show_preview(index, entry)
        self._controls()

    def _inspect(self):
        entries = [p['entry'] for p in self.panels]
        if not all(entries):
            return
        self.inspect_window = filefile_window(entries[0]['path'], entries[1]['path'], self)
        self._inspection_paths = [e['path'] for e in entries]
        self.inspect_window.pathsChanged.connect(self._pair_changed)
        self.inspect_window.show()

    def _pair_changed(self, path_a, path_b):
        updated = self.result
        if not updated:
            self._inspection_paths = [path_a, path_b]
            return
        known = {e['path']: e for key in ('common', 'only_a', 'only_b', 'uncertain')
                 for group in updated[key] for side in 'AB' for e in group[side]}
        for source, destination in zip(self._inspection_paths, (path_a, path_b)):
            if source == destination:
                continue
            snapshots = {}
            if destination:
                try:
                    signature = file_signature(destination)
                    expected = known.get(source, {}).get('signature')
                    snapshots[destination] = signature if expected and signature[2:4] == expected[2:4] else None
                except OSError:
                    snapshots[destination] = None
            updated = update_results(updated, 'move' if destination else 'trash',
                                     [(source, destination)], snapshots, self.roots, self.recursive)
        self._inspection_paths = [path_a, path_b]
        self.preview_cache.clear()
        self._scanned(updated, '', False)

    def _quick_look_entry(self, tree):
        item = tree.currentItem()
        if item is None or item.isHidden() or not item.isSelected():
            return None
        return (item.data(0, Qt.ItemDataRole.UserRole) or {}).get('entry')

    def _quick_look_menu(self, tree, point):
        if not quick_look.available() or self.busy or self.action_active:
            return
        item = tree.itemAt(point)
        if item is None or item.isHidden():
            return
        entry = (item.data(0, Qt.ItemDataRole.UserRole) or {}).get('entry')
        if not entry:
            return
        if not item.isSelected():
            tree.clearSelection()
        tree.setCurrentItem(item, 0, QItemSelectionModel.SelectionFlag.NoUpdate)
        item.setSelected(True)
        menu = QMenu(self)
        action = menu.addAction('Quick Look')
        action.triggered.connect(lambda: quick_look.show_preview(self, entry['path']))
        menu.exec(tree.viewport().mapToGlobal(point))

    def _double_clicked(self, item, column):
        data = item.data(0, Qt.ItemDataRole.UserRole) or {}
        if 'entry' in data:
            QDesktopServices.openUrl(QUrl.fromLocalFile(data['entry']['path']))
        elif data.get('group', {}).get('A') and data['group'].get('B'):
            self._inspect()

    def _set_groups_expanded(self, expanded):
        if self.busy or self.action_active:
            return
        tree = self.tabs.currentWidget()
        if tree is not None:
            tree.expandAll() if expanded else tree.collapseAll()

    def _update_result_tools(self, items):
        count = sum(not item.isHidden() and 'entry' in (item.data(0, Qt.ItemDataRole.UserRole) or {})
                    for item in items)
        self.selection_count.setText('No files selected' if not count else
                                     '1 file selected' if count == 1 else f'{count} files selected')
        tree = self.tabs.currentWidget()
        grouped = tree is not None and any(tree.topLevelItem(i).childCount() and not tree.topLevelItem(i).isHidden()
                                          for i in range(tree.topLevelItemCount()))
        for button in (self.expand_all, self.collapse_all):
            button.setEnabled(grouped and not self.busy and not self.action_active)

    def _uncertainty_causes(self, group=None):
        sides = set()
        for candidate in ([group] if group else (self.result or {}).get('uncertain', [])):
            sides.add('B' if candidate['A'] else 'A')
        return [note for note in (self.result or {}).get('notes', [])
                if note.get('uncertain') and note['side'] in sides]

    def _uncertainty_summary(self, causes):
        sides = ', '.join(sorted({note['side'] for note in causes}))
        issue = 'issue' if len(causes) == 1 else 'issues'
        folder = 'folders' if ',' in sides else 'folder'
        return (f'{len(causes)} scan {issue} in {folder} {sides or "A/B"}. '
                'These files were read, but may match content that could not be checked. '
                'Hidden files and folders are included in the explanation.')

    def _show_uncertainty_details(self):
        causes = self._uncertainty_causes()
        if not causes or self.busy or self.action_active:
            return
        message = QMessageBox(self)
        message.setWindowTitle('Why these results need checking')
        message.setIcon(QMessageBox.Icon.Information)
        message.setText('Some content in the other folder could not be checked.')
        message.setInformativeText('The files listed in Needs checking were read successfully, '
                                   'but we cannot confirm they are unique. '
                                   'Show Details lists the causes, including hidden files and folders.')
        message.setDetailedText('\n\n'.join(
            f"Folder {note['side']} · {note['path']}\n{note['reason']}" for note in causes))
        message.exec()

    def _controls(self):
        causes = self._uncertainty_causes()
        self.uncertainty_text.setText(self._uncertainty_summary(causes) if causes else '')
        self.uncertainty_notice.setVisible(bool(causes) and not self.busy
                                          and self.tabs.currentWidget() is self.trees['uncertain'])
        self.uncertainty_details.setEnabled(not self.busy and not self.action_active)
        entries = self._selection()
        items = self.tabs.currentWidget().selectedItems() if self.tabs.currentWidget() else []
        self._update_result_tools(items)
        individual_files = bool(items) and all('entry' in (item.data(0, Qt.ItemDataRole.UserRole) or {}) for item in items)
        available = bool(entries) and individual_files and not self.busy and not self.action_active
        verified = available and all(not e.get('not_compared') for e in entries)
        self.copy.setEnabled(verified)
        self.move.setEnabled(verified)
        self.trash.setEnabled(available)
        self.inspect.setEnabled(not self.busy and not self.action_active and all(p['entry'] and not p['entry'].get('not_compared') for p in self.panels))
        self.rescan.setEnabled(not self.busy and not self.action_active)
        transferring = getattr(self, '_transfer_running', False)
        self.stop.setText('Stop transfer' if transferring else 'Stop scan')
        self.stop.setToolTip('Stop after the current file; completed transfers remain in place.' if transferring else '')
        self.stop.setEnabled(self.busy or (transferring and not self._transfer_cancel.is_set()))
        if not self.busy:
            self.worker_panel.hide()
        self.scan_time.setVisible(self.busy)
        self.stop.setVisible(self.busy or transferring)
        self.progress.setVisible(self.busy or transferring)
        self.close_button.setEnabled(not self.action_active)
        self.tabs.setEnabled(not self.action_active)
        self.show_hidden.setEnabled(not self.action_active)
        self._bulk_controls()
        if hasattr(self, 'merge_button'):
            self.merge_button.setEnabled(bool(self.result) and bool(merged_entries(self.result)) and not self.busy and not self.action_active)
        for panel in self.panels:
            for key in ('open', 'reveal'):
                panel[key].setEnabled(bool(panel['entry']) and not self.action_active)

    def reject(self):
        if self.action_active:
            return
        if self.busy:
            self.scan_job.cancel.set()
        self.hover_timer.stop()
        self.hover_token += 1
        self.hover_popup.hide()
        self.scan_clock.stop()
        super().reject()

    def closeEvent(self, event):
        if self.action_active:
            event.ignore()
            return
        if self.busy:
            self.scan_job.cancel.set()
        self.hover_timer.stop()
        self.hover_token += 1
        self.hover_popup.hide()
        self.scan_clock.stop()
        super().closeEvent(event)

    def eventFilter(self, watched, event):
        if quick_look.available() and event.type() == QEvent.Type.KeyPress and event.key() == Qt.Key.Key_Space and event.modifiers() == Qt.KeyboardModifier.NoModifier:
            tree = self.tabs.currentWidget()
            if tree and watched in (tree, tree.viewport()) and not self.busy and not self.action_active:
                entry = self._quick_look_entry(tree)
                if entry:
                    if not event.isAutoRepeat():
                        self.hover_popup.hide()
                        self.hover_timer.stop()
                        quick_look.show_preview(self, entry['path'])
                    return True
        if hasattr(self, 'hover_popup') and event.type() == QEvent.Type.Leave:
            self.hover_popup.hide()
            self.hover_timer.stop()
            self.hover_token += 1
        elif hasattr(self, 'hover_popup') and event.type() == QEvent.Type.MouseMove:
            tree = self.tabs.currentWidget()
            if tree and watched == tree.viewport() and tree.itemAt(event.position().toPoint()) is None:
                self.hover_popup.hide()
                self.hover_timer.stop()
                self.hover_token += 1
        return super().eventFilter(watched, event)
