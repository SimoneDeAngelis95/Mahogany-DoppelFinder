from PIL import Image
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QGuiApplication, QIcon
from PyQt6.QtCore import QTimer
from main_window import MainWindow
from update_controller import UpdateController
import global_variables as GV
from style import APP_STYLE
import sys
import os
from pathlib import Path


def main():
    app = QApplication(sys.argv)
    app.setApplicationName(GV._APP_NAME_)
    app.setApplicationVersion(GV._VERSION_)
    resource_root = Path(os.environ["RESOURCEPATH"]) if os.environ.get("RESOURCEPATH") else Path(__file__).resolve().parent.parent
    app.setWindowIcon(QIcon(str(resource_root / "assets" / "icon.png")))
    app.setStyleSheet(APP_STYLE)
    # Load Pillow plugins on the GUI thread before parallel image/media probes.
    # py2app replaces Image.init with a loader that is unsafe when first called
    # concurrently by several decoder threads.
    Image.init()
    window = MainWindow()
    screen = QGuiApplication.primaryScreen()
    if screen:
        geometry = window.frameGeometry()
        geometry.moveCenter(screen.availableGeometry().center())
        window.move(geometry.topLeft())
    window.show()
    window.updates = UpdateController(window, GV._VERSION_)
    QTimer.singleShot(0, window.updates.check)
    return app.exec()


if __name__ == '__main__':
    sys.exit(main())
