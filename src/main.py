from PyQt6.QtWidgets import QApplication, QMessageBox
from PyQt6.QtGui import QGuiApplication
from uppie import Uppie
from main_window import MainWindow
import global_variables as GV
from style import APP_STYLE
import sys

app = QApplication(sys.argv)
app.setApplicationName(GV._APP_NAME_)
app.setStyleSheet(APP_STYLE)

# ===== CHECK FOR UPDATES ======
updater = Uppie(
    repo_owner="SimoneDeAngelis95",
    repo_name="Mahogany-DoppelFinder",
    local_version=GV._VERSION_,
)

try:
    if updater.is_update_available():
        answer = QMessageBox.question(
            None,
            "Update available",
            "A new version is available. Do you want to download and install it now?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes and updater.update():
            QMessageBox.information(
                None,
                "Update ready",
                "The update is ready. Close the application to complete the installation.",
            )
except Exception as error:
    QMessageBox.warning(
        None,
        "Update check failed",
        f"The application could not check for updates.\n\n{error}",
    )
# ==============================

myWindow = MainWindow()

# to center the window on the screen
screenGeometry = QGuiApplication.primaryScreen().availableGeometry()
windowGeometry = myWindow.frameGeometry()
windowGeometry.moveCenter(screenGeometry.center())
myWindow.move(windowGeometry.topLeft())

myWindow.show()

if __name__ == "__main__":
    app.exec()


# IDEA: USA TIPO SEI THREAD PER FARE I CONFRONTI
