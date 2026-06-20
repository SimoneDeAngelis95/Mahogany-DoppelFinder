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

    def __init__(self, parent, side):
        super().__init__(parent=parent)

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
        self.setStyleSheet("border: 1px solid black; border-radius: 5px;")

        self.setAcceptDrops(True)                                                       # This method enables the widget to accept drag and drop events.


    # ====== DIALOG ======
    def openChoosePathDialog(self):
        if self.getType() == "Empty":
            return
        
        dialog = QFileDialog()
        current_path = self.getPath()
        
        if self.getType() == "Folder":
            new_path = dialog.getExistingDirectory(self, "Choose Folder", GV._DEFAULT_FOLDER_PATH_)
        elif self.getType() == "File":
            filter_string = ""
            for ext in GV._ALL_ALLOWED_EXTENSIONS_:
                filter_string += "*" + str(ext) + ";;"                                                # this creates a filter string for the file dialog that includes all allowed extensions, separated by ";;". For example, it will look like "*.jpg;;*.jpeg;;*.png;;..."
            filter_string = filter_string[:-2]                                                        # remove the last ";;" from the filter string otherwise the dialog will show an empty filter at the end

            new_path, _ = dialog.getOpenFileName(self, "Choose File", filter=filter_string, directory=GV._DEFAULT_FOLDER_PATH_) # returns a tuple (file_path, selected_filter), we only need the file_path so we use _ to ignore the second value

        self.loadPath(new_path if new_path else current_path)                                         # if the user cancels the dialog, new_path will be an empty string, so we use current_path to keep the previous path

    # ====== GETTERS ======
    def getPath(self):
        return self.lbl_path.text() if os.path.exists(self.lbl_path.text()) else ""                   # returns the path displayed in the label if it exists

    def getType(self):
        return self.cmb_type.currentText()                                                            # returns the current text of the combo box, which indicates the type (Folder, File, Empty) selected by the user
    
    # ====== SETs ======
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
    def _Slot_TypeChanged(self):                                            # This slot is called when the user changes the type in the combo box. It emits the typeChanged signal and updates the icon and label accordingly.
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
        file_extension = os.path.splitext(path)[1].lower()                  # returns the file extension of the path in lowercase (e.g., ".jpg", ".mp4", etc.)
        
        if os.path.isdir(path):
            self.last_folder_path = path
        else:
            if file_extension in GV._ALL_ALLOWED_EXTENSIONS_:
                self.last_file_path = path
                self.lbl_path.setText(self.last_folder_path)
            else:
                return False
        
        if os.path.isdir(path) and (self.getType() == "File" or self.getType() == "Empty"):                  # if the path is a folder but the type is set to file or empty, change the type to folder
            self.setType("Folder")
        elif not os.path.isdir(path) and (self.getType() == "Folder" or self.getType() == "Empty"):          # if the path is a file but the type is set to folder or empty, change the type to file
            self.setType("File")
        
        self.lbl_path.setText(path)
        return True

    # =========================
    # ====== DRAG & DROP ======
    # =========================
    def dragEnterEvent(self, event: QDragEnterEvent):                       # this event is called when the user drags a file or folder over the widget but has not yet dropped it. It checks if the dragged item is a valid folder or file and accepts or ignores the event accordingly.
        url = event.mimeData().urls()[0]                                    # get the first URL from the list of paths in the mime data of the drag event
        path = url.toLocalFile()                                            # convert the QUrl object to a string

        if not os.path.isdir(path):
            file_extension = os.path.splitext(path)[1].lower()              # returns the file extension of the path in lowercase (e.g., ".jpg", ".mp4", etc.)
            if not file_extension in GV._ALL_ALLOWED_EXTENSIONS_:
                event.ignore()
                return
        event.acceptProposedAction()

    def dragLeaveEvent(self, event: QDragLeaveEvent):                       # event is called when the user drags a file or folder out of the widget without dropping it. It simply calls the parent class's dragLeaveEvent method to handle the event.
        return super().dragLeaveEvent(event)

    def dropEvent(self, event: QDropEvent):                                 # event that is called when the user drops a file or folder onto the widget. It retrieves the path of the dropped item and calls the loadPath method to load it into the widget.
        url = event.mimeData().urls()[0]
        path = str(url.toLocalFile())
        self.loadPath(path)