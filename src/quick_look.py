"""Platform-neutral entry point for the native macOS Quick Look panel."""
from pathlib import Path
import sys
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QMessageBox


def available():
    return sys.platform == 'darwin'


def _make_preview(owner):
    # Never import Cocoa/PyObjC on Windows or Linux.
    from _quick_look_macos import NativePreview
    return NativePreview(owner)


def close_preview(owner):
    preview = getattr(owner, '_quick_look_preview', None)
    if preview is not None:
        try:
            preview.close()
        except Exception:
            pass


def show_preview(owner, path):
    if not available() or getattr(owner, 'busy', False) or getattr(owner, 'action_active', False):
        return False
    path = Path(path).absolute()
    if not path.is_file():
        QMessageBox.warning(owner, 'Quick Look unavailable', 'The selected file is no longer available.')
        return False
    try:
        preview = getattr(owner, '_quick_look_preview', None)
        if preview is None:
            preview = _make_preview(owner)
            owner._quick_look_preview = preview
            owner.finished.connect(lambda _: close_preview(owner))
        preview.show(str(path))
        return True
    except Exception as error:
        close_preview(owner)
        dialog = QMessageBox(owner)
        dialog.setWindowTitle('Quick Look unavailable')
        dialog.setIcon(QMessageBox.Icon.Warning)
        dialog.setTextFormat(Qt.TextFormat.PlainText)
        dialog.setText('macOS could not open the native preview.')
        dialog.setDetailedText(f'{type(error).__name__}: {error}')
        dialog.setStandardButtons(QMessageBox.StandardButton.Ok)
        dialog.exec()
        return False


def navigate_preview(owner, direction):
    """Consume plain arrows in an open panel, even when selection forbids navigation."""
    if not available():
        return False
    preview = getattr(owner, '_quick_look_preview', None)
    if preview is None or not preview.is_open():
        return False
    if getattr(owner, 'busy', False) or getattr(owner, 'action_active', False):
        return True
    try:
        preview.navigate(direction)
    except Exception as error:
        close_preview(owner)
        QMessageBox.warning(owner, 'Quick Look unavailable',
                            f'The preview could not be updated: {error}')
    return True
