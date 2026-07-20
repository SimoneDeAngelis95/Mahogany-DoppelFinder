from PyQt6.QtWidgets import QWidget
from PyQt6.QtWidgets import QPushButton
from PyQt6.QtWidgets import QRadioButton
from PyQt6.QtWidgets import QVBoxLayout
from PyQt6.QtWidgets import QHBoxLayout
from PyQt6.QtWidgets import QCheckBox
from widget_choose_path import ChoosePathWidget
import global_variables as GV
import labels as LBL
#from Win_fileAndFile import Win_fileAndFile


class MainWindow(QWidget):

    def __init__(self):
        super().__init__()
        self.setObjectName("mainWindow")
        
        self.setWindowTitle(LBL.LABEL_MAIN_WINDOW_TITLE_) 

        self.ChoosePathA = ChoosePathWidget(self, "A")
        self.ChoosePathA.typeChanged.connect(self.setOperation)
        self.ChoosePathA.pathChanged.connect(self.setOperation)

        self.ChoosePathB = ChoosePathWidget(self, "B")
        self.ChoosePathB.typeChanged.connect(self.setOperation)
        self.ChoosePathB.pathChanged.connect(self.setOperation)

        # ====== CHECKBOXES ======
        self.chk_pics = QCheckBox(self)
        self.chk_pics.setText(LBL.CHK_ONLY_PICS_TEXT_)
        self.chk_pics.setChecked(True)
        self.chk_vids = QCheckBox(self)
        self.chk_vids.setText(LBL.CHK_ONLY_VIDS_TEXT_)
        self.chk_vids.setChecked(True)
        self.chk_audio = QCheckBox(self)
        self.chk_audio.setText(LBL.CHK_ONLY_AUDIO_TEXT_)
        self.chk_audio.setChecked(True)

        # ====== COMPARE BUTTON ======
        self.btn_compare = QPushButton(self)
        self.btn_compare.setObjectName("compareButton")
        self.setOperation()
        self.btn_compare.clicked.connect(self.doSomething)

        # ====== LAYOUT ======
        self.lyt_main = QVBoxLayout(self)
        self.lyt_folderSelectors = QHBoxLayout()
        self.lyt_folderSelectors.addWidget(self.ChoosePathA)
        self.lyt_folderSelectors.addWidget(self.ChoosePathB)
        self.lyt_main.addLayout(self.lyt_folderSelectors)
        self.lyt_checkboxes = QHBoxLayout()
        self.lyt_checkboxes.addWidget(self.chk_pics)
        self.lyt_checkboxes.addWidget(self.chk_vids)
        self.lyt_checkboxes.addWidget(self.chk_audio)
        self.lyt_main.addLayout(self.lyt_checkboxes)
        self.lyt_main.addWidget(self.btn_compare)
        
        self.setFixedSize(self.sizeHint())                                                        # disable resizing of the window and set it to the minimum size needed to fit all the widgets

    def setOperation(self):
        type_a = self.ChoosePathA.getType()
        type_b = self.ChoosePathB.getType()
        path_a = self.ChoosePathA.getPath()
        path_b = self.ChoosePathB.getPath()

        if type_a == "Folder" and type_b == "Folder":
            self.btn_compare.setText("Compare Folders")
        elif type_a == "File" and type_b == "File":
            self.btn_compare.setText("Compare Files")
        elif type_a == "Empty" and type_b == "Empty":
            self.btn_compare.setText("No Actions Available")
        elif type_a == "Empty" or type_b == "Empty":
            self.btn_compare.setText("Search for Duplicates")
        else:
            self.btn_compare.setText("Search File in Folder")

        has_required_paths = (
            (type_a == "Empty" or bool(path_a))
            and (type_b == "Empty" or bool(path_b))
        )
        self.btn_compare.setEnabled(
            not (type_a == "Empty" and type_b == "Empty") and has_required_paths
        )

    def doSomething(self):                                                                        # nome scherzoso per la funzione che esegue l'operazione corrente
        if self.ChoosePathA.getType() == "Folder" and self.ChoosePathB.getType() == "Folder":     # se entrambe le scelte sono cartelle
            pass                                                                                  # TODO: implementare la funzione per le cartelle
        elif self.ChoosePathA.getType() == "File" and self.ChoosePathB.getType() == "File":       # se entrambe le scelte sono cartelle
            pass #self.Win_FiFi.exec()                                                                  # avvia la finestra di confronto
        else:                                                                                     # se una scelta è un file e l'altra è una cartella a prescindere da quale sia quale
            pass                                                                                  # TODO: implementare la funzione per il file e la cartella
