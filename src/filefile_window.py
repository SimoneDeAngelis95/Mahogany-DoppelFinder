from dialog_position import configure_result_window, place_result_window
"""Two-file comparison dialog and explicit, reversible file actions."""
import errno
import os
from pathlib import Path
import shutil
import subprocess
import sys

from PIL import Image, UnidentifiedImageError
from PyQt6.QtCore import QObject, QRunnable, QThreadPool, QTimer, QUrl, Qt, pyqtSignal
from PyQt6.QtGui import QDesktopServices, QPixmap
from PyQt6.QtWidgets import (
    QDialog, QFrame, QHBoxLayout, QLabel, QMessageBox, QPushButton,
    QScrollArea, QVBoxLayout, QWidget,
)
from PyQt6.QtCore import QFile

from comparers.StaticImageComparer import StaticImageComparer
from comparers.MultiFrameImageComparer import MultiFrameImageComparer
from comparers.AudioComparer import AudioComparer
from comparers.VideoComparer import VideoComparer
from FFmpegAdapter import FFmpegAdapter


def file_signature(path):
    """Detect replacements and changes since the comparison was started."""
    info = os.stat(path)
    return (info.st_dev, info.st_ino, info.st_size, info.st_mtime_ns, info.st_ctime_ns)


def file_kind(path):
    try:
        with Image.open(path) as image:
            kind = 'animation' if getattr(image, 'n_frames', 1) > 1 else 'image'
        comparer = MultiFrameImageComparer() if kind == 'animation' else StaticImageComparer()
        validate = (comparer.is_valid_multi_frame_image if kind == 'animation'
                    else comparer.is_valid_static_image)
        if not validate(path):
            raise ValueError('The image cannot be decoded.')
        return kind
    except UnidentifiedImageError:
        pass
    info = FFmpegAdapter().get_media_info(path)
    if info['video_stream_count'] > 0:
        if VideoComparer().is_valid_video_file(path):
            return 'video'
    elif info['audio_stream_count'] == 1:
        if AudioComparer().is_valid_audio_file(path):
            return 'audio'
    raise ValueError('Unsupported or unreadable media file.')


def compare_files(path_a, path_b):
    """Reuse the existing content comparers; do not treat decode errors as differences."""
    for path in (path_a, path_b):
        if not Path(path).is_file():
            raise ValueError('One of the selected files no longer exists.')
    before = (file_signature(path_a), file_signature(path_b))
    if os.path.samefile(path_a, path_b):
        return 'same', before
    kinds = (file_kind(path_a), file_kind(path_b))
    if kinds[0] != kinds[1]:
        equal = False
    elif kinds[0] == 'image':
        equal = StaticImageComparer().compare_two_images(path_a, path_b)
    elif kinds[0] == 'animation':
        equal = MultiFrameImageComparer().compare_two_images(path_a, path_b)
    elif kinds[0] == 'audio':
        equal = AudioComparer().compare_two_audio_files(path_a, path_b)
    else:
        equal = VideoComparer().compare_two_video_files(path_a, path_b)
    if before != (file_signature(path_a), file_signature(path_b)):
        raise ValueError('A file changed during comparison. Compare the files again.')
    return ('equal' if equal else 'different'), before


def move_without_overwrite(source, destination, expected):
    """Reserve destination atomically, preserving existing files even on a name collision."""
    source, destination = Path(source), Path(destination)
    if source.is_symlink():
        raise ValueError('Moving symbolic links is not supported here.')
    if file_signature(source) != expected:
        raise ValueError('The source file changed. Compare the files again.')
    created = False
    try:
        try:
            os.link(source, destination)  # Atomic no-overwrite move within one filesystem.
            created = True
            # Creating a hard link changes ctime, but must not change the content.
            linked = file_signature(source)
            if linked[:4] != expected[:4]:
                raise ValueError('The source file changed during the move.')
        except OSError as error:
            if error.errno != errno.EXDEV:
                raise
            with source.open('rb') as incoming, destination.open('xb') as outgoing:
                created = True
                shutil.copyfileobj(incoming, outgoing, length=1024 * 1024)
                outgoing.flush()
                os.fsync(outgoing.fileno())
            if file_signature(source) != expected:
                raise ValueError('The source file changed during the move.')
            shutil.copystat(source, destination)
            linked = expected
        if file_signature(source) != linked:
            raise ValueError('The source file changed during the move.')
        source.unlink()
    except Exception:
        if created:
            destination.unlink(missing_ok=True)
        raise
    return str(destination)


class _Signals(QObject):
    done = pyqtSignal(object, str)


class _Job(QRunnable):
    def __init__(self, function):
        super().__init__()
        self.function = function
        self.signals = _Signals()

    def run(self):
        try:
            result, error = self.function(), ''
        except Exception as exception:
            result, error = None, str(exception) or type(exception).__name__
        self.signals.done.emit(result, error)


class filefile_window(QDialog):
    pathsChanged = pyqtSignal(str, str)

    def showEvent(self, event):
        super().showEvent(event)
        if not getattr(self, '_initial_position_set', False):
            self._initial_position_set = True
            QTimer.singleShot(0, lambda: place_result_window(self, large=False))

    def __init__(self, path_a, path_b, parent=None):
        super().__init__(parent)
        self.setWindowTitle('File File Comparison')
        self.setObjectName('fileComparisonWindow')
        configure_result_window(self)
        self.resize(800, 630)
        self.paths = [os.path.abspath(os.fspath(path_a)), os.path.abspath(os.fspath(path_b))]
        self.signatures = None
        self.state = 'pending'
        self.busy = False
        self._operation_active = False
        self.cards = []
        self.setStyleSheet('''
            QDialog#fileComparisonWindow { background: #f4f7fb; color: #27364a; }
            QFrame#fileCard { background: white; border: 1px solid #dce3ec; border-radius: 14px; }
            QLabel { color: #27364a; }
            QLabel#result { font-size: 24px; font-weight: 600; }
            QLabel#filename { font-size: 16px; font-weight: 600; }
            QPushButton { padding: 9px 12px; border: 1px solid #cfd8e3; border-radius: 8px;
                          background: white; color: #27364a; }
            QPushButton:hover { background: #eaf3f7; }
            QPushButton:disabled { color: #9aa6b5; background: #f5f7fa; }
            QPushButton#trash { color: #a34040; }
        ''')
        main = QVBoxLayout(self)
        main.setContentsMargins(24, 24, 24, 20)
        main.setSpacing(16)
        self.lbl_result = QLabel('Comparing files…')
        self.lbl_result.setObjectName('result')
        main.addWidget(self.lbl_result)
        self.lbl_detail = QLabel('Checking the decoded content. You can close this window while the comparison runs.')
        self.lbl_detail.setWordWrap(True)
        self.lbl_detail.setTextFormat(Qt.TextFormat.PlainText)
        main.addWidget(self.lbl_detail)
        content = QWidget()
        row = QHBoxLayout(content)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(16)
        for index, side in enumerate(('A', 'B')):
            card = QFrame()
            card.setObjectName('fileCard')
            layout = QVBoxLayout(card)
            layout.setContentsMargins(18, 18, 18, 18)
            heading = QLabel(f'FILE {side}')
            heading.setStyleSheet('color: ' + ('#276675' if index == 0 else '#52677f') + '; font-weight: 600;')
            layout.addWidget(heading)
            name = QLabel(); name.setObjectName('filename'); name.setWordWrap(True)
            name.setTextFormat(Qt.TextFormat.PlainText)
            layout.addWidget(name)
            preview = QLabel(); preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
            preview.setMinimumHeight(120)
            layout.addWidget(preview)
            info = QLabel(); info.setWordWrap(True)
            info.setTextFormat(Qt.TextFormat.PlainText)
            layout.addWidget(info)
            path = QLabel(); path.setWordWrap(True); path.setTextFormat(Qt.TextFormat.PlainText)
            path.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            path.setStyleSheet('color: #64748b; font-size: 12px;')
            layout.addWidget(path)
            layout.addStretch()
            open_button = QPushButton('Open file')
            open_button.clicked.connect(lambda checked=False, i=index: self._open(i))
            layout.addWidget(open_button)
            reveal = QPushButton('Show in Finder' if sys.platform == 'darwin' else 'Open containing folder')
            reveal.clicked.connect(lambda checked=False, i=index: self._reveal(i))
            layout.addWidget(reveal)
            move = QPushButton(f'Move {side} to folder of {"B" if index == 0 else "A"}')
            move.clicked.connect(lambda checked=False, i=index: self._move(i))
            layout.addWidget(move)
            trash = QPushButton(f'Move {side} to Trash'); trash.setObjectName('trash')
            trash.clicked.connect(lambda checked=False, i=index: self._trash(i))
            layout.addWidget(trash)
            self.cards.append(dict(name=name, preview=preview, info=info, path=path,
                                   open=open_button, reveal=reveal, move=move, trash=trash))
            row.addWidget(card, 1)
        scroll = QScrollArea(); scroll.setWidgetResizable(True); scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setWidget(content); main.addWidget(scroll, 1)
        self.btn_eraseA, self.btn_eraseB = (card['trash'] for card in self.cards)
        footer = QHBoxLayout()
        self.btn_retry = QPushButton('Compare again'); self.btn_retry.clicked.connect(self._compare)
        footer.addWidget(self.btn_retry); footer.addStretch()
        self.btn_close = QPushButton('Close'); self.btn_close.clicked.connect(self.close)
        footer.addWidget(self.btn_close); main.addLayout(footer)
        self._refresh()
        self._compare()

    def _launch(self, function, callback):
        self.busy = True
        self._refresh()
        self._job = _Job(function)
        self._job.signals.done.connect(callback)
        QThreadPool.globalInstance().start(self._job)

    def _compare(self):
        if self.busy or not all(self.paths):
            return
        self.state = 'pending'; self.signatures = None
        self.lbl_result.setText('Comparing files…')
        self.lbl_detail.setText('Checking decoded content with the existing media comparers.')
        paths = tuple(self.paths)
        self._launch(lambda: compare_files(*paths), self._compared)

    def _compared(self, result, error):
        self.busy = False
        if error:
            self.state = 'error'
            self.lbl_result.setText('Comparison could not be completed')
            self.lbl_detail.setText(error)
        else:
            self.state, self.signatures = result
            texts = {
                'equal': ('Same content', 'The current comparer found matching decoded content. File sizes and metadata may differ.'),
                'different': ('Different content', 'The files do not match under the current comparer’s rules, including its format and timing checks.'),
                'same': ('You selected the same file', 'Both paths refer to the same file. File actions are disabled.'),
            }
            title, detail = texts[self.state]
            self.lbl_result.setText(title); self.lbl_detail.setText(detail)
        self._refresh()

    def _refresh(self):
        for index, card in enumerate(self.cards):
            path = self.paths[index]
            exists = bool(path) and Path(path).is_file()
            card['name'].setText(Path(path).name if path else f'File {"AB"[index]} removed')
            card['path'].setText(path or 'Moved to Trash')
            card['preview'].clear()
            if exists:
                try:
                    size = Path(path).stat().st_size
                    card['info'].setText(f'{Path(path).suffix.upper().lstrip(".") or "File"} · {size:,} bytes')
                    # Qt reads one preview frame; audio/video can be opened externally.
                    if size <= 20 * 1024 * 1024:
                        pixmap = QPixmap(path)
                        if not pixmap.isNull():
                            card['preview'].setPixmap(pixmap.scaled(240, 140, Qt.AspectRatioMode.KeepAspectRatio,
                                                                  Qt.TransformationMode.SmoothTransformation))
                        else:
                            card['preview'].setText('Preview in your default app')
                    else:
                        card['preview'].setText('Preview in your default app')
                except OSError:
                    exists = False
                    card['info'].setText('File unavailable')
            else:
                card['info'].setText('File unavailable')
            card['open'].setEnabled(exists and not self.busy)
            card['reveal'].setEnabled(exists and not self.busy)
            actionable = exists and not self.busy and self.state in ('equal', 'different')
            card['trash'].setEnabled(actionable and not Path(path).is_symlink())
            other = self.paths[1 - index]
            different_folders = bool(path and other) and Path(path).parent != Path(other).parent
            card['move'].setEnabled(actionable and bool(other) and Path(other).is_file()
                                    and different_folders and not Path(path).is_symlink())
        self.btn_close.setEnabled(not self._operation_active)
        self.btn_retry.setEnabled(not self.busy and all(bool(p) and Path(p).is_file() for p in self.paths))

    def _check_unchanged(self):
        try:
            if self.signatures is None or not all(self.paths):
                raise ValueError('Compare the files before taking an action.')
            if os.path.samefile(*self.paths):
                raise ValueError('Both paths now refer to the same file.')
            if tuple(file_signature(p) for p in self.paths) != self.signatures:
                raise ValueError('A file changed since comparison. Compare again before taking an action.')
            if any(Path(p).is_symlink() for p in self.paths):
                raise ValueError('File actions on symbolic links are not supported here.')
            return True
        except (OSError, ValueError) as error:
            self.state = 'error'; self.lbl_result.setText('Files changed or unavailable')
            self.lbl_detail.setText(str(error)); self._refresh()
            return False

    def _open(self, index):
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(self.paths[index])):
            QMessageBox.warning(self, 'Could not open file', 'No application could open the selected file.')

    def _reveal(self, index):
        try:
            if sys.platform == 'darwin':
                subprocess.Popen(['open', '-R', self.paths[index]])
            elif not QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(self.paths[index]).parent))):
                raise OSError('Could not open the containing folder.')
        except OSError as error:
            QMessageBox.warning(self, 'Could not show file', str(error))

    def _move(self, index):
        if self.busy or not self._check_unchanged():
            return
        source = Path(self.paths[index]); destination = Path(self.paths[1-index]).parent / source.name
        if source.parent == destination.parent:
            return
        if os.path.lexists(destination):
            QMessageBox.warning(self, 'Name already exists', f'Nothing was moved. A file with this name already exists:\n\n{destination}')
            return
        if QMessageBox.question(self, 'Move file', f'Move this file?\n\nFrom: {source}\nTo: {destination}',
                                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            return
        if not self._check_unchanged():
            return
        expected = self.signatures[index]
        self._operation_active = True
        self.lbl_result.setText('Moving file…')
        self._action_index = index
        self._launch(lambda: move_without_overwrite(source, destination, expected), self._moved)

    def _moved(self, path, error):
        self.busy = False
        self._operation_active = False
        if error:
            self._action_failed(error)
        else:
            self.paths[self._action_index] = path
            self.pathsChanged.emit(*self.paths)
            self._compare()

    def _trash(self, index):
        if self.busy or not self._check_unchanged():
            return
        path = self.paths[index]
        if QMessageBox.question(self, 'Move to Trash', f'Move file {"AB"[index]} to Trash?\n\n{path}\n\nYou can restore it from Trash.',
                                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            return
        if not self._check_unchanged():
            return
        expected = self.signatures[index]
        def trash():
            if file_signature(path) != expected:
                raise ValueError('The file changed. Compare again before taking an action.')
            file = QFile(path)
            if not file.moveToTrash():
                raise OSError(file.errorString() or 'The system could not move this file to Trash.')
            return index
        self._operation_active = True
        self.lbl_result.setText('Moving file to Trash…')
        self._launch(trash, self._trashed)

    def _trashed(self, index, error):
        self.busy = False
        self._operation_active = False
        if error:
            self._action_failed(error)
        else:
            self.paths[index] = ''; self.state = 'removed'; self.signatures = None
            self.lbl_result.setText(f'File {"AB"[index]} moved to Trash')
            self.lbl_detail.setText('The other file was kept. You can restore the removed file from Trash.')
            self.pathsChanged.emit(*self.paths); self._refresh()

    def _action_failed(self, error):
        self.state = 'error'; self.signatures = None
        self.lbl_result.setText('The operation could not be completed')
        self.lbl_detail.setText(error); self._refresh()

    def closeEvent(self, event):
        # Keep the parent blocked until a file action finishes and paths are synchronized.
        if self._operation_active:
            event.ignore()
        else:
            super().closeEvent(event)

    def reject(self):
        # Escape uses reject() directly, bypassing closeEvent().
        if not self._operation_active:
            super().reject()
