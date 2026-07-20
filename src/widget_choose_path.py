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

# Qframe is a subclass of QWidget that adds functionality for managing borders and frames around the widget.
# It is useful when you want to add a visual frame around a widget or group of widgets.
# You can customize the style and spacing of the frame.

# This class is the widget that allows the user to choose a path (folder or file) and displays the selected path.
# It also supports drag and drop functionality for selecting paths.
# The widget consists of a combo box to select the type (Folder, File, Empty), a button to open a file/folder dialog, and a label to display the selected path.
# The widget emits a signal when the type is changed, allowing other parts of the application to respond accordingly.

class ChoosePathWidget(QFrame):
    typeChanged = pyqtSignal()
    pathChanged = pyqtSignal()

    def __init__(self, parent, side):
        super().__init__(parent=parent)
        self.setObjectName("pathCard")

        self.iconFolderPath = getattr(GV, f'_ICON_FOLDER_{side}_')      # getattr is used to dynamically access the icon paths based on the side (A or B) passed to the constructor. It retrieves the appropriate icon path from the global variables module (GV) for the folder, file, and empty icons.
        self.iconFilePath = getattr(GV, f'_ICON_FILE_{side}_')
        self.iconEmptyPath = getattr(GV, f'_ICON_EMPTY_{side}_')
        self.last_folder_path = ""                                      # variables used to keep track of changes (see checkCurrentPath function)
        self.last_file_path = ""

        self.setFixedWidth(GV._CHOSE_PATH_WIDGET_WIDTH_)
        self.setFixedHeight(GV._CHOSE_PATH_WIDGET_HEIGHT_)

        self.cmb_type = QComboBox(self)
        self.cmb_type.addItems(GV._ALLOWED_TYPES_)
        self.cmb_type.currentTextChanged.connect(self._Slot_TypeChanged)

        self.btn_choose = QPushButton(self)
        self.btn_choose.setObjectName("pathButton")
        self.btn_choose.setIconSize(QSize(100, 100))
        self.btn_choose.clicked.connect(self.openChoosePathDialog)
        self.updateIcon()

        self.lbl_path = QLabel(self)
        self.lbl_path.setObjectName("pathLabel")
        self.lbl_path.setMaximumHeight(40)
        self.lbl_path.setFont(QFont("Arial", 15))
        self.lbl_path.setText("")

        self.scr_scrollArea = QScrollArea()
        self.scr_scrollArea.setObjectName("pathScrollArea")
        self.scr_scrollArea.setWidget(self.lbl_path)
        self.scr_scrollArea.setWidgetResizable(True)
        self.scr_scrollArea.setMaximumHeight(50)

        # ====== LAYOUT ======
        self.lyt_main = QVBoxLayout(self)
        self.lyt_main.addWidget(self.cmb_type)
        self.lyt_main.setSpacing(10)
        self.lyt_main.addWidget(self.btn_choose)
        self.lyt_main.setAlignment(self.btn_choose, Qt.AlignmentFlag.AlignCenter)
        self.lyt_main.setSpacing(5)
        self.lyt_main.addWidget(self.scr_scrollArea)

        self.setAcceptDrops(True)                                                       # This method enables the widget to accept drag and drop events.


    # ====== DIALOG ======
    def openChoosePathDialog(self):
        if self.getType() == "Empty":
            return

        current_path = self.getPath()
        initial_directory = GV._DEFAULT_FOLDER_PATH_
        if current_path:
            initial_directory = current_path if os.path.isdir(current_path) else os.path.dirname(current_path)

        if self.getType() == "Folder":
            new_path = QFileDialog.getExistingDirectory(self, "Choose Folder", initial_directory)
        elif self.getType() == "File":
            filter_string = ";;".join(f"*{ext}" for ext in GV._ALL_ALLOWED_EXTENSIONS_)
            new_path, _ = QFileDialog.getOpenFileName(
                self,
                "Choose File",
                directory=initial_directory,
                filter=filter_string,
            )

        if new_path:
            self.loadPath(new_path)

    # ====== GETTERS ======
    def getPath(self):
        return self.lbl_path.text() if os.path.exists(self.lbl_path.text()) else ""                   # returns the path displayed in the label if it exists

    def getType(self):
        return self.cmb_type.currentText()                                                            # returns the current text of the combo box, which indicates the type (Folder, File, Empty) selected by the user
    
    # ====== SETs ======
    def setType(self, path_type):
        if path_type not in GV._ALLOWED_TYPES_:
            raise ValueError(f"Unsupported path type: {path_type}")
        self.cmb_type.setCurrentText(path_type)

    def updateIcon(self):
        is_empty = self.getType() == "Empty"
        icons = {
            "Folder": self.iconFolderPath,
            "File": self.iconFilePath,
            "Empty": self.iconEmptyPath,
        }
        icon_path = icons.get(self.getType(), self.iconEmptyPath)

        self.btn_choose.setProperty("empty", is_empty)
        self.btn_choose.setIcon(QIcon(icon_path))
        self.btn_choose.style().unpolish(self.btn_choose)
        self.btn_choose.style().polish(self.btn_choose)

    # ====== CHECKs ======
    def _Slot_TypeChanged(self):                                            # This slot is called when the user changes the type in the combo box. It emits the typeChanged signal and updates the icon and label accordingly.
        self.updateIcon()

        if self.getType() == "File":
            if not os.path.isfile(self.last_file_path):
                self.last_file_path = ""
            self.lbl_path.setText(self.last_file_path)
        elif self.getType() == "Folder":
            if not os.path.isdir(self.last_folder_path):
                self.last_folder_path = ""
            self.lbl_path.setText(self.last_folder_path)
        elif self.getType() == "Empty":
            self.lbl_path.setText("")

        self.typeChanged.emit()

    # ====== ADD PATH ======
    def loadPath(self, path):
        if not path or not os.path.exists(path):
            return False

        if os.path.isdir(path):
            self.last_folder_path = path
            path_type = "Folder"
        elif os.path.isfile(path):
            file_extension = os.path.splitext(path)[1].lower()
            if file_extension not in GV._ALL_ALLOWED_EXTENSIONS_:
                return False
            self.last_file_path = path
            path_type = "File"
        else:
            return False

        if self.getType() != path_type:
            self.setType(path_type)

        self.lbl_path.setText(path)
        self.pathChanged.emit()
        return True

    # =========================
    # ====== DRAG & DROP ======
    # =========================
    def dragEnterEvent(self, event: QDragEnterEvent):                       # this event is called when the user drags a file or folder over the widget but has not yet dropped it. It checks if the dragged item is a valid folder or file and accepts or ignores the event accordingly.
        path = self._getFirstLocalPath(event)

        if path is None:
            event.ignore()
            return

        if not os.path.exists(path):
            event.ignore()
            return

        if os.path.isfile(path):
            file_extension = os.path.splitext(path)[1].lower()              # returns the file extension of the path in lowercase (e.g., ".jpg", ".mp4", etc.)
            if file_extension not in GV._ALL_ALLOWED_EXTENSIONS_:
                event.ignore()
                return
        elif not os.path.isdir(path):
            event.ignore()
            return
        event.acceptProposedAction()

    def dragLeaveEvent(self, event: QDragLeaveEvent):                       # event is called when the user drags a file or folder out of the widget without dropping it. It simply calls the parent class's dragLeaveEvent method to handle the event.
        return super().dragLeaveEvent(event)

    def dropEvent(self, event: QDropEvent):                                 # event that is called when the user drops a file or folder onto the widget. It retrieves the path of the dropped item and calls the loadPath method to load it into the widget.
        path = self._getFirstLocalPath(event)

        if path is None:
            event.ignore()
            return

        if self.loadPath(path):
            event.acceptProposedAction()
        else:
            event.ignore()

    def _getFirstLocalPath(self, event):                                    # this function is used to extract the first local file path from the mime data of a drag and drop event. It checks if the mime data contains URLs and if the first URL is a local file. If so, it returns the local file path; otherwise, it returns None.
        mime_data = event.mimeData()

        if not mime_data.hasUrls():
            return None

        urls = mime_data.urls()
        if not urls or not urls[0].isLocalFile():
            return None

        path = urls[0].toLocalFile()
        return path if path else None
