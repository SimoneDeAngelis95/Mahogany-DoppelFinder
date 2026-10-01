from dialog_position import configure_result_window, place_result_window
"""Folder comparison, grouped results, asynchronous previews and explicit file actions."""
from collections import OrderedDict
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading

from PyQt6.QtCore import (QEvent, QPoint, QFile, QObject, QRunnable,
                         QThreadPool, QTimer, QUrl, Qt, pyqtSignal)
from PyQt6.QtGui import QCursor, QDesktopServices, QImage, QImageReader, QPixmap
from PyQt6.QtWidgets import (QDialog, QFrame, QHBoxLayout, QLabel, QMessageBox,
                            QProgressBar, QPushButton, QSplitter, QTabWidget,
                            QTreeWidget, QTreeWidgetItem, QVBoxLayout, QWidget,
                            QAbstractItemView, QComboBox, QMenu, QSizePolicy)
from filefile_window import _Job, file_signature, filefile_window, move_without_overwrite
from folder_scan import ScanCancelled, scan_folders
from FFmpegAdapter import FFmpegAdapter


def copy_without_overwrite(source, destination, expected):
    source, destination = Path(source), Path(destination)
    if source.is_symlink() or file_signature(source) != expected:
        raise ValueError('The source file changed. Scan again.')
    created = False
    try:
        with source.open('rb') as incoming, destination.open('xb') as outgoing:
            created = True
            shutil.copyfileobj(incoming, outgoing, length=1024 * 1024)
            outgoing.flush(); os.fsync(outgoing.fileno())
        if file_signature(source) != expected:
            raise ValueError('The source file changed during copying.')
        shutil.copystat(source, destination)
    except Exception:
        if created:
            destination.unlink(missing_ok=True)
        raise
    return str(destination)


def preview_file(entry):
    path = entry['path']
    if file_signature(path) != entry['signature']:
        raise ValueError('File changed. Scan again to update the preview.')
    image = QImage()
    detail = ''
    if entry['kind'] in ('image', 'animation'):
        reader = QImageReader(path)
        reader.setAutoTransform(True)
        size = reader.size()
        if size.isValid():
            detail = f'{size.width()} × {size.height()} pixels'
            size.scale(640, 360, Qt.AspectRatioMode.KeepAspectRatio)
            reader.setScaledSize(size)
        image = reader.read()
        if image.isNull():
            raise ValueError(reader.errorString() or 'Image preview unavailable')
    elif entry['kind'] == 'video':
        adapter = FFmpegAdapter()
        info = adapter.get_video_info(path)
        detail = f'{info["width"]} × {info["height"]} pixels'
        if info['duration'] is not None:
            detail += f' · {info["duration"]:.1f} s'
        result = subprocess.run([adapter.ffmpeg_path, '-v', 'error', '-i', path,
                                 '-map', '0:V:0', '-frames:v', '1', '-vf',
                                 'scale=640:360:force_original_aspect_ratio=decrease',
                                 '-f', 'image2pipe', '-c:v', 'png', '-'],
                                capture_output=True, stdin=subprocess.DEVNULL, timeout=20)
        if result.returncode:
            raise ValueError('Video preview unavailable')
        image = QImage.fromData(result.stdout)
        if image.isNull():
            raise ValueError('No video frame available')
    else:
        info = FFmpegAdapter().get_audio_info(path)
        detail = f'{info["sample_rate"]} Hz · {info["channels"]} channels'
        if info['duration'] is not None:
            detail += f' · {info["duration"]:.1f} s'
    if file_signature(path) != entry['signature']:
        raise ValueError('File changed during preview. Scan again.')
    return image, detail


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


def verify_bulk_entry(entry):
    if Path(entry['path']).is_symlink() or file_signature(entry['path']) != entry['signature']:
        raise ValueError('File changed. Scan again.')
    for copy in entry.get('keep_copies', []):
        if Path(copy['path']).is_symlink() or file_signature(copy['path'])[:4] != copy['signature'][:4]:
            raise ValueError('A matching copy in the other folder changed or disappeared. Scan again.')


class _ScanSignals(QObject):
    progress = pyqtSignal(int, int, str)
    done = pyqtSignal(object, str, bool)


class _ScanJob(QRunnable):
    def __init__(self, roots, recursive, categories, workers=0):
        super().__init__()
        self.roots, self.recursive, self.categories = roots, recursive, categories
        self.workers = workers
        self.cancel = threading.Event()
        self.signals = _ScanSignals()

    def run(self):
        try:
            result = scan_folders(*self.roots, self.recursive, self.categories,
                                  self.cancel, self.signals.progress.emit, self.workers)
            self.signals.done.emit(result, '', False)
        except ScanCancelled:
            self.signals.done.emit(None, '', True)
        except Exception as error:
            self.signals.done.emit(None, str(error), False)


class folderfolder_window(QDialog):
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
        self.busy = False; self.action_active = False; self.result = None
        self.preview_cache = OrderedDict(); self.preview_tokens = [0, 0]; self.hover_token = 0
        self._preview_jobs = {}; self._pending_previews = {}; self._preview_serial = 0
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
        main = QVBoxLayout(self); main.setContentsMargins(16, 16, 16, 14); main.setSpacing(8)
        self.title = QLabel('Compare folder contents'); self.title.setStyleSheet('font-size: 22px; font-weight: 600;')
        main.addWidget(self.title)
        paths = QLabel('A  '+self.roots[0]+'\nB  '+self.roots[1])
        paths.setTextFormat(Qt.TextFormat.PlainText); paths.setWordWrap(True)
        paths.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse); main.addWidget(paths)
        self.status = QLabel(); self.status.setWordWrap(True); self.status.setTextFormat(Qt.TextFormat.PlainText)
        main.addWidget(self.status)
        progress_row = QHBoxLayout(); self.progress = QProgressBar(); progress_row.addWidget(self.progress, 1)
        self.stop = QPushButton('Stop scan'); self.stop.clicked.connect(self._stop); progress_row.addWidget(self.stop)
        main.addLayout(progress_row)
        self.splitter = QSplitter(Qt.Orientation.Vertical)
        self.tabs = QTabWidget(); self.tabs.setMinimumHeight(240); self.trees = {}
        for key, name in [('common', 'In common'), ('only_a', 'Only in A'), ('only_b', 'Only in B'), ('uncertain', 'Needs checking'), ('notes', 'Not compared')]:
            tree = QTreeWidget(); tree.setColumnCount(3); tree.setHeaderLabels(['File', 'Reason', ''] if key == 'notes' else ['File A', 'File B', 'Copies'])
            tree.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
            tree.setMouseTracking(True)
            tree.viewport().installEventFilter(self)
            tree.itemSelectionChanged.connect(self._selected)
            tree.itemEntered.connect(self._hover)
            tree.itemDoubleClicked.connect(self._double_clicked)
            self.trees[key] = tree; self.tabs.addTab(tree, name)
        self.tabs.currentChanged.connect(self._selected)
        self.splitter.addWidget(self.tabs)
        panel = QWidget(); panel_layout = QHBoxLayout(panel); panel_layout.setContentsMargins(0, 0, 0, 0)
        self.panels = []
        for side, color in [('A', '#276675'), ('B', '#52677f')]:
            card = QFrame(); card.setObjectName('previewCard'); layout = QVBoxLayout(card); layout.setContentsMargins(10, 8, 10, 8); layout.setSpacing(4)
            heading = QLabel('FILE '+side); heading.setStyleSheet('font-weight: 600; color: '+color); layout.addWidget(heading)
            name = QLabel('Select a file or content group'); name.setWordWrap(True); name.setMaximumHeight(34); name.setTextFormat(Qt.TextFormat.PlainText); layout.addWidget(name)
            picture = QLabel(); picture.setAlignment(Qt.AlignmentFlag.AlignCenter); picture.setMinimumHeight(60); picture.setMaximumHeight(95); picture.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored); layout.addWidget(picture, 1)
            info = QLabel(); info.setWordWrap(True); info.setTextFormat(Qt.TextFormat.PlainText); layout.addWidget(info)
            path = QLabel(); path.setWordWrap(True); path.setMaximumHeight(30); path.setTextFormat(Qt.TextFormat.PlainText)
            path.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse); path.setStyleSheet('font-size: 11px; color: #64748b;'); layout.addWidget(path)
            buttons = QHBoxLayout(); open_button = QPushButton('Open file'); reveal = QPushButton('Show in Finder' if sys.platform=='darwin' else 'Show folder')
            open_button.clicked.connect(lambda checked=False, s=side: self._open_panel(s))
            reveal.clicked.connect(lambda checked=False, s=side: self._reveal_panel(s))
            buttons.addWidget(open_button); buttons.addWidget(reveal); layout.addLayout(buttons)
            self.panels.append(dict(name=name, picture=picture, info=info, path=path, open=open_button, reveal=reveal, entry=None))
            open_button.setEnabled(False); reveal.setEnabled(False); panel_layout.addWidget(card, 1)
        self.splitter.addWidget(panel)
        self.splitter.setChildrenCollapsible(False); self.splitter.setHandleWidth(8)
        self.splitter.setStretchFactor(0, 1); self.splitter.setStretchFactor(1, 0)
        self.splitter.setSizes([480, 210]); main.addWidget(self.splitter, 1)
        actions = QHBoxLayout(); self.copy = QPushButton('Copy to other folder'); self.move = QPushButton('Move to other folder'); self.trash = QPushButton('Move to Trash')
        self.trash.setStyleSheet('QPushButton { color: #a34040; } QPushButton:disabled { color: #9aa6b5; }')
        for button, operation in [(self.copy, 'copy'), (self.move, 'move'), (self.trash, 'trash')]:
            button.clicked.connect(lambda checked=False, op=operation: self._action(op)); actions.addWidget(button)
        self.inspect = QPushButton('Compare displayed A / B'); self.inspect.clicked.connect(self._inspect); actions.addWidget(self.inspect)
        main.addLayout(actions)
        bulk = QFrame(); bulk.setObjectName('bulkActions')
        bulk.setStyleSheet('QFrame#bulkActions { background: #eaf0f5; border-radius: 10px; }')
        bulk_layout = QVBoxLayout(bulk)
        bulk_row = QHBoxLayout()
        bulk_row.addWidget(QLabel('Whole-folder actions'))
        self.bulk_media = QComboBox()
        for label, category in [('All scanned media', 'all'), ('Photos & images', 'images'), ('Audio', 'audio'), ('Videos', 'video')]:
            self.bulk_media.addItem(label, category)
        self.bulk_media.currentIndexChanged.connect(self._bulk_controls)
        bulk_row.addWidget(self.bulk_media); bulk_row.addStretch()
        self.bulk_buttons = {}; self.bulk_menu_actions = {}
        for side, color in [('A', '#276675'), ('B', '#52677f')]:
            button = QPushButton('Folder '+side+' actions ▾')
            button.setStyleSheet('color: '+color+'; font-weight: 600;')
            menu = QMenu(button)
            for operation, scope in [('trash', 'matching'), ('move', 'unique'), ('copy', 'unique')]:
                action = menu.addAction('')
                action.triggered.connect(lambda checked=False, s=side, op=operation, sc=scope: self._bulk_action(s, op, sc))
                self.bulk_menu_actions[(side, operation)] = action
            button.setMenu(menu); self.bulk_buttons[side] = button; bulk_row.addWidget(button)
        bulk_layout.addLayout(bulk_row)
        self.bulk_hint = QLabel(); self.bulk_hint.setWordWrap(True); self.bulk_hint.setStyleSheet('color: #64748b; font-size: 12px;')
        bulk_layout.addWidget(self.bulk_hint); main.addWidget(bulk)
        footer = QHBoxLayout(); self.rescan = QPushButton('Scan again'); self.rescan.clicked.connect(self._scan); footer.addWidget(self.rescan); footer.addStretch()
        self.close_button = QPushButton('Close'); self.close_button.clicked.connect(self.close); footer.addWidget(self.close_button); main.addLayout(footer)
        self.hover_timer = QTimer(self); self.hover_timer.setSingleShot(True); self.hover_timer.setInterval(400)
        self.hover_timer.timeout.connect(self._hover_ready)
        self.hover_popup = QFrame(self, Qt.WindowType.ToolTip)
        self.hover_popup.setObjectName("hoverPopup")
        self.hover_popup.setStyleSheet("QFrame#hoverPopup { background: white; border: 1px solid #dce3ec; border-radius: 8px; } QLabel { border: none; }")
        hover_layout = QVBoxLayout(self.hover_popup)
        self.hover_picture = QLabel(); self.hover_name = QLabel(); self.hover_detail = QLabel()
        self.hover_name.setTextFormat(Qt.TextFormat.PlainText)
        self.hover_detail.setTextFormat(Qt.TextFormat.PlainText)
        for label in (self.hover_picture, self.hover_name, self.hover_detail): hover_layout.addWidget(label)
        self.hover_hide_timer = QTimer(self); self.hover_hide_timer.setSingleShot(True)
        self.hover_hide_timer.timeout.connect(self.hover_popup.hide)
        self._controls(); self._scan()

    def _scan(self):
        if self.busy or self.action_active: return
        self.busy = True; self.result = None; self.preview_cache.clear()
        self.hover_timer.stop(); self.hover_token += 1; self.hover_popup.hide()
        for tree in self.trees.values(): tree.clear()
        self._selected(); self.title.setText('Scanning folder contents…'); self.progress.setRange(0, 0)
        self._controls()
        self.scan_job = _ScanJob(tuple(self.roots), self.recursive, set(self.categories), self.workers)
        self.scan_job.signals.progress.connect(self._progress)
        self.scan_job.signals.done.connect(self._scanned)
        QThreadPool.globalInstance().start(self.scan_job)

    def _progress(self, value, total, text):
        if self.scan_job.cancel.is_set(): return
        self.progress.setRange(0, total if total else 0); self.progress.setValue(value); self.status.setText(text)

    def _stop(self):
        self.scan_job.cancel.set(); self.stop.setEnabled(False)
        self.status.setText('Stopping after the current media check…')

    def _scanned(self, result, error, cancelled):
        self.busy = False; self.progress.setRange(0, 1); self.progress.setValue(1 if result else 0)
        if cancelled:
            self.title.setText('Scan stopped'); self.status.setText('No incomplete results are shown. Scan again when ready.')
        elif error:
            self.title.setText('Scan could not be completed'); self.status.setText(error)
        else:
            self.result = result; self.title.setText('Folder comparison complete')
            self.status.setText(f'{len(result["common"])} content groups in common · {len(result["only_a"])} only in A · {len(result["only_b"])} only in B · {len(result["uncertain"])} need checking · {len(result["notes"])} not compared')
            self._populate()
        self._controls()

    def _populate(self):
        names = ['In common', 'Only in A', 'Only in B', 'Needs checking', 'Not compared']
        for index, (key, tree) in enumerate(self.trees.items()):
            tree.clear(); self.tabs.setTabText(index, f'{names[index]} ({len(self.result[key])})')
            if key == 'notes':
                for note in self.result[key]:
                    item = QTreeWidgetItem([note['side']+' · '+Path(note['path']).name, note['reason'], ''])
                    item.setToolTip(0, note['path']); tree.addTopLevelItem(item)
            else:
                for number, group in enumerate(self.result[key], 1):
                    title = ('Matching content' if key=='common' else 'Unverified match' if key=='uncertain' else 'Content group')+f' {number}'
                    parent = QTreeWidgetItem([title, '', f'{len(group["A"])} A · {len(group["B"])} B'])
                    parent.setData(0, Qt.ItemDataRole.UserRole, {'group': group}); tree.addTopLevelItem(parent)
                    for side in ('A', 'B'):
                        for entry in group[side]:
                            relative = str(Path(entry['path']).relative_to(self.roots['AB'.index(side)]))
                            child = QTreeWidgetItem([relative if side=='A' else '', relative if side=='B' else '', side])
                            child.setData(0, Qt.ItemDataRole.UserRole, {'entry': entry, 'group': group})
                            parent.addChild(child)
                    parent.setExpanded(number <= 3)
            tree.setColumnWidth(0, 370); tree.setColumnWidth(1, 370)
        if self.trees['common'].topLevelItemCount():
            self.trees['common'].setCurrentItem(self.trees['common'].topLevelItem(0))
        self._selected()

    def _selection(self):
        tree = self.tabs.currentWidget(); entries = {}
        if tree is None: return []
        for item in tree.selectedItems():
            data = item.data(0, Qt.ItemDataRole.UserRole) or {}
            if 'entry' in data: values = [data['entry']]
            elif 'group' in data: values = data['group']['A'] + data['group']['B']
            else: values = []
            for entry in values: entries[(entry['side'], entry['path'])] = entry
        return list(entries.values())

    def _selected(self):
        tree = self.tabs.currentWidget(); selected = tree.selectedItems() if tree else []
        data = (selected[0].data(0, Qt.ItemDataRole.UserRole) or {}) if selected else {}
        group = data.get('group', {'A': [], 'B': []})
        for index, side in enumerate(('A', 'B')):
            entry = data.get('entry')
            if not entry or entry['side'] != side: entry = group[side][0] if group[side] else None
            self._show_preview(index, entry)
        self._controls()

    def _preview_async(self, entry, callback):
        key = (entry['path'], entry['signature'])
        try:
            if file_signature(entry['path']) != entry['signature']: raise ValueError('File changed. Scan again.')
        except (OSError, ValueError) as error:
            callback(None, str(error)); return
        if key in self.preview_cache:
            self.preview_cache.move_to_end(key); callback(self.preview_cache[key], ''); return
        if key in self._pending_previews:
            self._pending_previews[key].append(callback); return
        self._pending_previews[key] = [callback]
        serial = self._preview_serial; self._preview_serial += 1
        job = _Job(lambda: preview_file(entry)); self._preview_jobs[serial] = job
        def completed(result, error):
            self._preview_jobs.pop(serial, None)
            if not error:
                self.preview_cache[key] = result
                while len(self.preview_cache) > 32: self.preview_cache.popitem(last=False)
            for pending in self._pending_previews.pop(key, []): pending(result, error)
        job.signals.done.connect(completed)
        QThreadPool.globalInstance().start(job)

    def _show_preview(self, index, entry):
        panel = self.panels[index]; panel['entry'] = entry; self.preview_tokens[index] += 1
        token = self.preview_tokens[index]; panel['picture'].clear(); panel['info'].clear()
        panel['name'].setText(Path(entry['path']).name if entry else 'No file on this side')
        panel['path'].setText(entry['path'] if entry else '')
        panel['path'].setToolTip(entry['path'] if entry else '')
        panel['name'].setToolTip(Path(entry['path']).name if entry else '')
        panel['open'].setEnabled(bool(entry) and not self.action_active)
        panel['reveal'].setEnabled(bool(entry) and not self.action_active)
        if not entry: return
        panel['picture'].setText('Loading preview…')
        if entry['kind']=='audio': panel['open'].setText('Listen in default app')
        else: panel['open'].setText('Open file')
        def ready(result, error):
            if token != self.preview_tokens[index]: return
            if error: panel['picture'].setText('Preview unavailable'); panel['info'].setText(error); return
            image, detail = result
            if image.isNull(): panel['picture'].setText('♫')
            else: panel['picture'].setPixmap(QPixmap.fromImage(image).scaled(350, 85, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
            panel['info'].setText(detail+f' · {entry["signature"][2]:,} bytes')
        self._preview_async(entry, ready)

    def _hover(self, item, column):
        self.hover_popup.hide(); self.hover_token += 1; self.hover_item = item; self.hover_tree = self.tabs.currentWidget()
        self.hover_timer.start()

    def _hover_ready(self):
        tree = self.hover_tree; item = self.hover_item
        if tree != self.tabs.currentWidget() or tree.itemAt(tree.viewport().mapFromGlobal(QCursor.pos())) != item: return
        data = item.data(0, Qt.ItemDataRole.UserRole) or {}; entry = data.get('entry')
        if not entry: return
        token = self.hover_token
        def ready(result, error):
            if token != self.hover_token or tree.itemAt(tree.viewport().mapFromGlobal(QCursor.pos())) != item: return
            if error: return
            image, detail = result
            self.hover_picture.clear()
            if not image.isNull():
                self.hover_picture.setPixmap(QPixmap.fromImage(image).scaled(200, 120, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
            self.hover_name.setText(Path(entry['path']).name)
            self.hover_detail.setText(detail)
            self.hover_popup.adjustSize()
            point = QCursor.pos() + QPoint(14, 18)
            bounds = self.screen().availableGeometry()
            point.setX(min(point.x(), bounds.right() - self.hover_popup.width()))
            point.setY(min(point.y(), bounds.bottom() - self.hover_popup.height()))
            self.hover_popup.move(point); self.hover_popup.show(); self.hover_hide_timer.start(3500)
        self._preview_async(entry, ready)

    def _open_panel(self, side):
        entry = self.panels['AB'.index(side)]['entry']
        if entry and not QDesktopServices.openUrl(QUrl.fromLocalFile(entry['path'])):
            QMessageBox.warning(self, 'Could not open file', 'No application could open this file.')

    def _reveal_panel(self, side):
        entry = self.panels['AB'.index(side)]['entry']
        if not entry: return
        try:
            if sys.platform=='darwin': subprocess.Popen(['open', '-R', entry['path']])
            elif not QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(entry['path']).parent))): raise OSError('Could not open folder')
        except OSError as error: QMessageBox.warning(self, 'Could not show file', str(error))

    def _inspect(self):
        entries = [p['entry'] for p in self.panels]
        if not all(entries): return
        self.inspect_window = filefile_window(entries[0]['path'], entries[1]['path'], self)
        self.inspect_window.pathsChanged.connect(lambda *args: self._scan())
        self.inspect_window.show()

    def _double_clicked(self, item, column):
        data = item.data(0, Qt.ItemDataRole.UserRole) or {}
        if 'entry' in data:
            QDesktopServices.openUrl(QUrl.fromLocalFile(data['entry']['path']))
        elif data.get('group', {}).get('A') and data['group'].get('B'):
            self._inspect()

    def _controls(self):
        entries = self._selection()
        items = self.tabs.currentWidget().selectedItems() if self.tabs.currentWidget() else []
        individual_files = bool(items) and all('entry' in (item.data(0, Qt.ItemDataRole.UserRole) or {}) for item in items)
        available = bool(entries) and individual_files and not self.busy and not self.action_active
        self.copy.setEnabled(available); self.move.setEnabled(available); self.trash.setEnabled(available)
        self.inspect.setEnabled(not self.busy and not self.action_active and all(p['entry'] for p in self.panels))
        self.rescan.setEnabled(not self.busy and not self.action_active)
        self.stop.setEnabled(self.busy)
        self.stop.setVisible(self.busy); self.progress.setVisible(self.busy)
        self.close_button.setEnabled(not self.action_active)
        self.tabs.setEnabled(not self.action_active)
        self._bulk_controls()
        for panel in self.panels:
            for key in ('open', 'reveal'): panel[key].setEnabled(bool(panel['entry']) and not self.action_active)

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

    def _action(self, operation, entries=None, scope_label=None):
        if self.busy or self.action_active: return
        is_bulk = entries is not None
        entries = list(entries) if is_bulk else self._selection()
        if not entries: return
        # A whole content group is a browsing convenience, not an implicit delete selection.
        selected = self.tabs.currentWidget().selectedItems()
        if not is_bulk and any('entry' not in (item.data(0, Qt.ItemDataRole.UserRole) or {}) for item in selected):
            QMessageBox.information(self, 'Select individual files', 'Select the file rows you want to act on, rather than the whole content group.'); return
        identities = set(); plan = []; conflicts = []
        for entry in entries:
            source = Path(entry['path']); destination = None
            if os.path.realpath(source) in identities: continue
            identities.add(os.path.realpath(source))
            try:
                verify_bulk_entry(entry)
                if operation != 'trash':
                    # Preserve the relative folder structure under the opposite selected root.
                    source_root = Path(self.roots['AB'.index(entry['side'])]); target_root = Path(self.roots[1-'AB'.index(entry['side'])])
                    destination = target_root / source.relative_to(source_root)
                    ancestor = destination.parent
                    while ancestor != ancestor.parent:
                        if ancestor.is_symlink(): raise ValueError('Destination contains a symbolic link')
                        ancestor = ancestor.parent
                    if source.absolute() == destination.absolute(): raise ValueError('Source and destination are the same')
                    if os.path.lexists(destination): raise ValueError('Destination name already exists')
                    if any(d == destination for _, d in plan): raise ValueError('More than one file has the same destination')
                plan.append((entry, destination))
            except (OSError, ValueError) as error: conflicts.append(source.name+': '+str(error))
        if conflicts:
            QMessageBox.warning(self, 'Resolve conflicts first', 'Nothing was changed.\n\n'+'\n'.join(conflicts[:12])); return
        verb = {'copy': 'Copy', 'move': 'Move', 'trash': 'Move to Trash'}[operation]
        lines = [e['path']+(('\n  → '+str(d)) if d else '') for e,d in plan]
        total_bytes = sum(e['signature'][2] for e, _ in plan)
        message = f'{verb} {len(plan)} file(s) · {total_bytes:,} bytes?\n'
        if scope_label: message += scope_label+'\n'
        message += '\n'+'\n\n'.join(lines[:8])
        if len(plan)>8: message += f'\n\n…and {len(plan)-8} more files.'
        if operation=='trash':
            message += '\n\nSelected files will go to the system Trash.'
            if is_bulk: message += getattr(self, 'keep_message', '\nMatching copies in the opposite folder are kept.')
        else: message += '\n\nRelative subfolders are preserved. Existing files are never overwritten.'
        confirmation = QMessageBox(self)
        confirmation.setWindowTitle(verb); confirmation.setText(message)
        confirmation.setTextFormat(Qt.TextFormat.PlainText)
        confirmation.setDetailedText("\n\n".join(lines))
        confirmation.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        confirmation.setDefaultButton(QMessageBox.StandardButton.No)
        if confirmation.exec() != QMessageBox.StandardButton.Yes: return
        self.action_active = True; self.status.setText(verb+' in progress…'); self._controls()
        def perform():
            successes = []; errors = []
            if is_bulk:
                # Recheck the entire plan after confirmation before changing any file.
                try:
                    for entry, _ in plan: verify_bulk_entry(entry)
                except (OSError, ValueError) as error:
                    return [], ['Nothing was changed: '+str(error)]
            for entry, destination in plan:
                try:
                    source = entry['path']
                    verify_bulk_entry(entry)
                    if operation=='trash':
                        file = QFile(source)
                        if not file.moveToTrash(): raise OSError(file.errorString() or 'System Trash unavailable')
                    else:
                        destination.parent.mkdir(parents=True, exist_ok=True)
                        function = copy_without_overwrite if operation=='copy' else move_without_overwrite
                        function(source, destination, entry['signature'])
                    successes.append(source)
                except Exception as error: errors.append(entry['path']+': '+str(error))
            return successes, errors
        self.action_job = _Job(perform); self.action_job.signals.done.connect(self._acted)
        QThreadPool.globalInstance().start(self.action_job)

    def _acted(self, result, error):
        self.action_active = False
        if error: QMessageBox.warning(self, 'Operation failed', error)
        elif result[1]: QMessageBox.warning(self, 'Operation finished with errors', f'{len(result[0])} file(s) processed.\n\n'+'\n'.join(result[1][:12]))
        self._scan()

    def reject(self):
        if self.action_active: return
        if self.busy: self.scan_job.cancel.set()
        self.hover_timer.stop(); self.hover_token += 1; self.hover_popup.hide()
        super().reject()

    def closeEvent(self, event):
        if self.action_active: event.ignore(); return
        if self.busy: self.scan_job.cancel.set()
        self.hover_timer.stop(); self.hover_token += 1; self.hover_popup.hide()
        super().closeEvent(event)

    def eventFilter(self, watched, event):
        if hasattr(self, 'hover_popup') and event.type() == QEvent.Type.Leave:
            self.hover_popup.hide(); self.hover_timer.stop(); self.hover_token += 1
        elif hasattr(self, 'hover_popup') and event.type() == QEvent.Type.MouseMove:
            tree = self.tabs.currentWidget()
            if tree and watched == tree.viewport() and tree.itemAt(event.position().toPoint()) is None:
                self.hover_popup.hide(); self.hover_timer.stop(); self.hover_token += 1
        return super().eventFilter(watched, event)
