from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QGuiApplication
from uppie import Uppie
from main_window import MainWindow
import global_variables as GV
import sys

app = QApplication(sys.argv)
app.setApplicationName(GV._APP_NAME_)

# ===== CHECK FOR UPDATES ======
updater = Uppie(
    repo_owner="SimoneDeAngelis95",
    repo_name="Mahogany-DoppelFinder",
    local_version=GV._VERSION_,
)

if updater.is_update_available():
    # TODO:Show a message box to the user indicating that an update is available
    # se l'utente accetta, scarica e installa l'aggiornamento
    if updater.update():
        pass
        # aggiungi un messaggio che invita a chiudere l'app per installare l'update
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