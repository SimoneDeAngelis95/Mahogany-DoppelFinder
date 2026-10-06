"""Shared preview cards, hover previews and bounded in-memory media loading."""
from collections import OrderedDict
from pathlib import Path
import subprocess
import sys

from PyQt6.QtCore import QPoint, QThreadPool, QTimer, Qt
from PyQt6.QtGui import QCursor, QImage, QImageReader, QPixmap
from PyQt6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QSizePolicy, QVBoxLayout, QWidget

from desktop_files import open_file, reveal_file
from filefile_window import _Job, file_signature
from FFmpegAdapter import FFmpegAdapter

PREVIEW_CACHE_LIMIT = 32

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


class ComparisonPreviews:
    """Preview behavior shared by each comparison dialog."""

    def _initialize_previews(self):
        self.preview_cache = OrderedDict()
        self.preview_tokens = [0, 0]
        self.hover_token = 0
        self._preview_jobs = {}
        self._pending_previews = {}
        self._preview_serial = 0
        self.hover_timer = QTimer(self)
        self.hover_timer.setSingleShot(True)
        self.hover_timer.setInterval(400)
        self.hover_timer.timeout.connect(self._hover_ready)
        self.hover_popup = QFrame(self, Qt.WindowType.ToolTip)
        self.hover_popup.setObjectName("hoverPopup")
        self.hover_popup.setStyleSheet("QFrame#hoverPopup { background: white; border: 1px solid #dce3ec; border-radius: 8px; } QLabel { border: none; }")
        hover_layout = QVBoxLayout(self.hover_popup)
        self.hover_picture = QLabel()
        self.hover_name = QLabel()
        self.hover_detail = QLabel()
        self.hover_name.setTextFormat(Qt.TextFormat.PlainText)
        self.hover_detail.setTextFormat(Qt.TextFormat.PlainText)
        for label in (self.hover_picture, self.hover_name, self.hover_detail):
            hover_layout.addWidget(label)
        self.hover_hide_timer = QTimer(self)
        self.hover_hide_timer.setSingleShot(True)
        self.hover_hide_timer.timeout.connect(self.hover_popup.hide)

    def _build_preview_panels(self):
        panel = QWidget()
        panel_layout = QHBoxLayout(panel)
        panel_layout.setContentsMargins(0, 0, 0, 0)
        self.panels = []
        for side, color in [('A', '#276675'), ('B', '#52677f')]:
            card = QFrame()
            card.setObjectName('previewCard')
            layout = QVBoxLayout(card)
            layout.setContentsMargins(10, 8, 10, 8)
            layout.setSpacing(4)
            heading = QLabel('FILE '+side)
            heading.setStyleSheet('font-weight: 600; color: '+color)
            layout.addWidget(heading)
            name = QLabel('Select a file or content group')
            name.setWordWrap(True)
            name.setMaximumHeight(34)
            name.setTextFormat(Qt.TextFormat.PlainText)
            layout.addWidget(name)
            picture = QLabel()
            picture.setAlignment(Qt.AlignmentFlag.AlignCenter)
            picture.setMinimumHeight(60)
            picture.setMaximumHeight(95)
            picture.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
            layout.addWidget(picture, 1)
            info = QLabel()
            info.setWordWrap(True)
            info.setTextFormat(Qt.TextFormat.PlainText)
            layout.addWidget(info)
            path = QLabel()
            path.setWordWrap(True)
            path.setMaximumHeight(30)
            path.setTextFormat(Qt.TextFormat.PlainText)
            path.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            path.setStyleSheet('font-size: 11px; color: #64748b;')
            layout.addWidget(path)
            buttons = QHBoxLayout()
            open_button = QPushButton('Open file')
            reveal = QPushButton('Show in Finder' if sys.platform=='darwin' else 'Show folder')
            open_button.clicked.connect(lambda checked=False, s=side: self._open_panel(s))
            reveal.clicked.connect(lambda checked=False, s=side: self._reveal_panel(s))
            buttons.addWidget(open_button)
            buttons.addWidget(reveal)
            layout.addLayout(buttons)
            self.panels.append(dict(name=name, picture=picture, info=info, path=path, open=open_button, reveal=reveal, entry=None))
            open_button.setEnabled(False)
            reveal.setEnabled(False)
            panel_layout.addWidget(card, 1)
        return panel

    def _preview_async(self, entry, callback):
        key = (entry['path'], entry['signature'])
        try:
            if file_signature(entry['path']) != entry['signature']:
                raise ValueError('File changed. Scan again.')
        except (OSError, ValueError) as error:
            callback(None, str(error))
            return
        if key in self.preview_cache:
            self.preview_cache.move_to_end(key)
            callback(self.preview_cache[key], '')
            return
        if key in self._pending_previews:
            self._pending_previews[key].append(callback)
            return
        self._pending_previews[key] = [callback]
        serial = self._preview_serial
        self._preview_serial += 1
        job = _Job(lambda: preview_file(entry))
        self._preview_jobs[serial] = job
        def completed(result, error):
            self._preview_jobs.pop(serial, None)
            if not error:
                self.preview_cache[key] = result
                while len(self.preview_cache) > PREVIEW_CACHE_LIMIT:
                    self.preview_cache.popitem(last=False)
            for pending in self._pending_previews.pop(key, []):
                pending(result, error)
        job.signals.done.connect(completed)
        QThreadPool.globalInstance().start(job)

    def _show_preview(self, index, entry):
        panel = self.panels[index]
        panel['entry'] = entry
        self.preview_tokens[index] += 1
        token = self.preview_tokens[index]
        panel['picture'].clear()
        panel['info'].clear()
        panel['name'].setText(Path(entry['path']).name if entry else 'No file on this side')
        panel['path'].setText(entry['path'] if entry else '')
        panel['path'].setToolTip(entry['path'] if entry else '')
        panel['name'].setToolTip(Path(entry['path']).name if entry else '')
        panel['open'].setEnabled(bool(entry) and not self.action_active)
        panel['reveal'].setEnabled(bool(entry) and not self.action_active)
        if not entry:
            return
        if entry.get('not_compared'):
            panel['picture'].setText('Not compared')
            panel['info'].setText(entry.get('reason', 'Preview unavailable'))
            panel['open'].setText('Open file')
            return
        panel['picture'].setText('Loading preview…')
        if entry['kind']=='audio':
            panel['open'].setText('Listen in default app')
        else:
            panel['open'].setText('Open file')
        def ready(result, error):
            if token != self.preview_tokens[index]:
                return
            if error:
                panel['picture'].setText('Preview unavailable')
                panel['info'].setText(error)
                return
            image, detail = result
            if image.isNull():
                panel['picture'].setText('♫')
            else:
                panel['picture'].setPixmap(QPixmap.fromImage(image).scaled(350, 85, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
            panel['info'].setText(detail+f' · {entry["signature"][2]:,} bytes')
        self._preview_async(entry, ready)

    def _hover(self, item, column):
        self.hover_popup.hide()
        self.hover_token += 1
        self.hover_item = item
        self.hover_tree = self.tabs.currentWidget()
        self.hover_timer.start()

    def _hover_ready(self):
        tree = self.hover_tree
        item = self.hover_item
        if tree != self.tabs.currentWidget() or tree.itemAt(tree.viewport().mapFromGlobal(QCursor.pos())) != item:
            return
        data = item.data(0, Qt.ItemDataRole.UserRole) or {}
        entry = data.get('entry')
        if not entry or entry.get('not_compared'):
            return
        token = self.hover_token
        def ready(result, error):
            if token != self.hover_token or tree.itemAt(tree.viewport().mapFromGlobal(QCursor.pos())) != item:
                return
            if error:
                return
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
            self.hover_popup.move(point)
            self.hover_popup.show()
            self.hover_hide_timer.start(3500)
        self._preview_async(entry, ready)

    def _open_panel(self, side):
        entry = self.panels['AB'.index(side)]['entry']
        if entry:
            open_file(self, entry['path'])

    def _reveal_panel(self, side):
        entry = self.panels['AB'.index(side)]['entry']
        if entry:
            reveal_file(self, entry['path'])
