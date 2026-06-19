from PyQt6.QtWidgets import QPushButton
from PyQt6.QtWidgets import QFileDialog
from PyQt6.QtWidgets import QLabel
from PyQt6.QtWidgets import QVBoxLayout
from PyQt6.QtWidgets import QFrame
from PyQt6.QtWidgets import QScrollArea
from PyQt6.QtWidgets import QComboBox
from PyQt6.QtGui import QDragLeaveEvent, QIcon
from PyQt6.QtGui import QFont
from PyQt6.QtGui import QDragEnterEvent
from PyQt6.QtGui import QDropEvent
from PyQt6.QtCore import pyqtSignal
from PyQt6.QtCore import QSize
from PyQt6.QtCore import Qt
import global_variables as GV
import os

# QFrame è una sottoclasse di QWidget che aggiunge funzionalità per la gestione dei bordi e delle cornici intorno al widget.
# È utile quando si desidera aggiungere una cornice visiva intorno a un widget o gruppo di widget.
# È possibile personalizzare lo stile e la spaziatura della cornice.

class ChoosePathWidget(QFrame):
    typeChanged = pyqtSignal()

    def __init__(self, parent, side):
        super().__init__(parent=parent)

        self.iconFolderPath = getattr(GV, f'_ICON_FOLDER_{side}_')  # getattr mi restituisce un attributo da un oggetto. In questo caso l'oggetto è il modulo GV e l'attributo è la f_string, in caso non ci fosse quel valore restituirebbe un errore (oppure un valore alternativo se indicato)
        self.iconFilePath = getattr(GV, f'_ICON_FILE_{side}_')
        self.iconEmptyPath = getattr(GV, f'_ICON_EMPTY_{side}_')
        self.last_folder_path = ""                                      # variabili usate per tenere memoria dei cambi (vedi funzione checkCurrentPath)
        self.last_file_path = ""

        self.setFixedWidth(300)
        self.setFixedHeight(200)

        self.cmb_type = QComboBox(self)
        self.cmb_type.addItems(["Folder", "File", "Empty"])
        self.cmb_type.currentTextChanged.connect(self._Slot_TypeChanged)

        self.btn_choose = QPushButton(self)
        self.btn_choose.setIconSize(QSize(100, 100))
        self.btn_choose.setStyleSheet("border: 0px;")
        self.btn_choose.clicked.connect(self.openChoosePathDialog)
        self.updateIcon()

        self.lbl_path = QLabel(self)
        self.lbl_path.setMaximumHeight(40)
        self.lbl_path.setFont(QFont("Arial", 15))
        self.lbl_path.setText("")
        self.lbl_path.setStyleSheet("border: 0px;")

        self.scr_scrollArea = QScrollArea()
        self.scr_scrollArea.setWidget(self.lbl_path)
        self.scr_scrollArea.setWidgetResizable(True)
        self.scr_scrollArea.setStyleSheet("border: 0px;")
        self.scr_scrollArea.setMaximumHeight(50)

        # ====== LAYOUT ======
        self.lyt_main = QVBoxLayout(self)
        self.lyt_main.addWidget(self.cmb_type)
        self.lyt_main.setSpacing(10)
        self.lyt_main.addWidget(self.btn_choose)
        self.lyt_main.setAlignment(self.btn_choose, Qt.AlignmentFlag.AlignCenter)
        self.lyt_main.setSpacing(5)
        self.lyt_main.addWidget(self.scr_scrollArea)

        # ====== STYLE ======
        self.setStyleSheet("border: 1px solid black; border-radius: 10px;")

        self.setAcceptDrops(True) # questo deve starci, altrimenti non funziona il Drag&Drop!


    # ====== FINESTRA SCELTA PATH ======
    def openChoosePathDialog(self):
        if self.getType() == "Empty":
            return
        
        dialog = QFileDialog()
        current_path = self.getPath()
        
        if self.getType() == "Folder":
            new_path = dialog.getExistingDirectory(self, "Choose Folder", GV._DEFAULT_FOLDER_PATH_)
        elif self.getType() == "File":
            filter_string = ""
            for ext in GV._IMG_ALLOWED_EXTENSIONS_:
                filter_string += "*" + str(ext) + ";;"    # creo un filtro per le immagini, che non è altro che una stringa
            filter_string = filter_string[:-2]            # rimuovo gli ultimi ;; superflui, altrimenti mi crea un opzione vuota

            new_path, _ = dialog.getOpenFileName(self, "Choose File", filter=filter_string, directory=GV._DEFAULT_FOLDER_PATH_) # restituisce due valori, il path e l'estensione del file, l'estensione non mi interessa e la butto in _

        self.loadPath(new_path if new_path else current_path)            # se è != da "" allora setta new_path, altrimenti last_path

    # ====== GETs ======
    def getPath(self):
        return self.lbl_path.text() if os.path.exists(self.lbl_path.text()) else ""

    def getType(self):
        return self.cmb_type.currentText()
    
    # ====== SETs ======
    # DEPRECATED!
    # ACHTUNG! non tiene conto della cartella empty!!!
    #def changeType(self):                                                               # se impostato su File imposta Folder e viceversa, da fare meglio
    #    self.cmb_type.setCurrentText("Folder" if self.getType() == "File" else "File")

    def setType(self, type):
        self.cmb_type.setCurrentText(type)

    def updateIcon(self):
        if self.getType() == "Folder":
            icon_path = self.iconFolderPath
        elif self.getType() == "File":
            icon_path = self.iconFilePath
        elif self.getType() == "Empty":
            icon_path = self.iconEmptyPath

        self.btn_choose.setIcon(QIcon(icon_path))

    # ====== CHECKs ======
    def _Slot_TypeChanged(self):
        self.typeChanged.emit()
        self.updateIcon()

        if self.getType() == "File":
            self.lbl_path.setText(self.last_file_path)
        elif self.getType() == "Folder":
            self.lbl_path.setText(self.last_folder_path)
        elif self.getType() == "Empty":
            self.lbl_path.setText("")

    # ====== ADD PATH ======
    def loadPath(self, path):
        file_extension = os.path.splitext(path)[1].lower()                   # mi restituisce come stringa (scritta in minuscolo) l'estensione del file
        
        if os.path.isdir(path):
            self.last_folder_path = path
        else:
            if file_extension in GV._IMG_ALLOWED_EXTENSIONS_:
                self.last_file_path = path
                self.lbl_path.setText(self.last_folder_path)
            else:
                return False
        
        if os.path.isdir(path) and (self.getType() == "File" or self.getType() == "Empty"):                  # se il path è una directory ma è impostato il file
            #self.changeType()
            self.setType("Folder")
        elif not os.path.isdir(path) and (self.getType() == "Folder" or self.getType() == "Empty"):          # se il path è un file ma è impostato su directory
            #self.changeType()
            self.setType("File")
        
        self.lbl_path.setText(path)
        return True

    # =========================
    # ====== DRAG & DROP ======
    # =========================
    def dragEnterEvent(self, event: QDragEnterEvent):          # evento che un file (o cartella) è trascinato sul widget ma non ancora rilasciato
        url = event.mimeData().urls()[0]                       # quando viene chiamato questo evento, viene passata una lista di elementi che sono gli elementi trascinati nel Widget, io posso buttarci dentro anche più file la volta, ma onde evitare problemi io andrò a prendere solamente il primo elemento di questa lista 
        path = url.toLocalFile()                               # converto l'oggetto Qurl in string

        if not os.path.isdir(path):
            file_extension = os.path.splitext(path)[1].lower() # mi restituisce come stringa (scritta in minuscolo) l'estensione del file
            if not file_extension in GV._IMG_ALLOWED_EXTENSIONS_:
                event.ignore()
                return
        event.acceptProposedAction()

    def dragLeaveEvent(self, event: QDragLeaveEvent):          # quando hai finito di trascinare file sullo spazio di Drag & Drop
        return super().dragLeaveEvent(event)

    def dropEvent(self, event: QDropEvent):                    # il file (o cartella) è stato rilasciato
        url = event.mimeData().urls()[0]
        path = str(url.toLocalFile())
        self.loadPath(path)