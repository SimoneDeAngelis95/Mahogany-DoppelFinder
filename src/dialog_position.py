"""Independent modal result windows, fitted to their parent's screen."""
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QWidget


def configure_result_window(window):
    # WindowModal becomes a native sheet on macOS. ApplicationModal with
    # an ordinary window keeps the main window blocked without the sheet.
    window.setWindowFlags(Qt.WindowType.Window | Qt.WindowType.WindowTitleHint |
                          Qt.WindowType.WindowSystemMenuHint | Qt.WindowType.WindowCloseButtonHint |
                          Qt.WindowType.WindowMaximizeButtonHint)
    window.setWindowModality(Qt.WindowModality.ApplicationModal)


def place_result_window(window, large=True):
    if not window.isVisible(): return
    parent = window.parentWidget()
    screen = parent.screen() if parent else window.screen()
    if not screen: return
    available = screen.availableGeometry()
    width = min(1280 if large else 800, int(available.width() * .90))
    height = int(available.height() * .92) if large else min(630, int(available.height() * .90))
    window.resize(width, height)
    frame = window.frameGeometry()
    # Coordinates include monitor offsets, including displays left of the primary one.
    left = available.left() + max(0, (available.width() - frame.width()) // 2)
    top = available.top() + max(0, (available.height() - frame.height()) // 2)
    QWidget.move(window, left, top)
