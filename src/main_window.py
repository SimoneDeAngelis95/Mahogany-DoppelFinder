from PyQt6.QtWidgets import QWidget
from PyQt6.QtWidgets import QPushButton
from PyQt6.QtWidgets import QVBoxLayout
from PyQt6.QtWidgets import QHBoxLayout
from PyQt6.QtWidgets import QCheckBox, QComboBox, QLabel
from widget_choose_path import ChoosePathWidget
import global_variables as GV
from filefile_window import filefile_window
from folderfolder_window import folderfolder_window
from filefolder_window import filefolder_window
from duplicates_window import duplicates_window


class MainWindow(QWidget):

    def __init__(self):
        super().__init__()
        self.setObjectName("mainWindow")
        
        self.setWindowTitle(f"{GV._APP_NAME_} - {GV._VERSION_}") 

        self.ChoosePathA = ChoosePathWidget(self, "A")
        self.ChoosePathA.typeChanged.connect(self.setOperation)
        self.ChoosePathA.pathChanged.connect(self.setOperation)

        self.ChoosePathB = ChoosePathWidget(self, "B")
        self.ChoosePathB.typeChanged.connect(self.setOperation)
        self.ChoosePathB.pathChanged.connect(self.setOperation)

        # ====== CHECKBOXES ======
        self.chk_pics = QCheckBox(self)
        self.chk_pics.setText("Pics")
        self.chk_pics.setChecked(True)
        self.chk_vids = QCheckBox(self)
        self.chk_vids.setText("Videos")
        self.chk_vids.setChecked(True)
        self.chk_audio = QCheckBox(self)
        self.chk_audio.setText("Audio")
        self.chk_audio.setChecked(True)

        self.chk_recursive = QCheckBox("Include subfolders", self)
        self.chk_recursive.setChecked(True)

        self.cmb_workers = QComboBox(self)
        for text, workers in [('Automatic', 0), ('1 file at a time', 1), ('Up to 2 files', 2), ('Up to 4 files', 4)]:
            self.cmb_workers.addItem(text, workers)
        self.cmb_workers.setToolTip('Automatic adapts to available memory and file type. Manual values are maximum limits; memory safeguards still apply.')


        # ====== COMPARE BUTTON ======
        self.btn_compare = QPushButton(self)
        self.btn_compare.setObjectName("compareButton")
        self.setOperation()
        self.btn_compare.clicked.connect(self.letsCompare)

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
        self.lyt_main.addWidget(self.chk_recursive)
        concurrency_row = QHBoxLayout()
        concurrency_row.addWidget(QLabel('Simultaneous comparisons'))
        concurrency_row.addWidget(self.cmb_workers)
        self.lyt_main.addLayout(concurrency_row)
        self.lyt_main.addWidget(self.btn_compare)
        
        self.setFixedSize(self.sizeHint()) # disable resizing of the window and set it to the minimum size needed to fit all the widgets

        # ====== OTHER WINDOWS ======
        self.filefile_win = None
        self.folderfolder_win = None
        self.filefolder_win = None
        self.duplicates_win = None

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
            self.btn_compare.setText("Find duplicates in folder" if "Folder" in (type_a, type_b) else "Choose a folder to find duplicates")
        else:
            self.btn_compare.setText("Search File in Folder")

        self.chk_recursive.setEnabled(type_a == "Folder" or type_b == "Folder")

        has_required_paths = (
            (type_a == "Empty" or bool(path_a))
            and (type_b == "Empty" or bool(path_b))
        )
        self.btn_compare.setEnabled(
            not (type_a == "Empty" and type_b == "Empty")
            and not ({type_a, type_b} == {"File", "Empty"}) and has_required_paths
        )

    def letsCompare(self):
        if self.ChoosePathA.getType() == "Folder" and self.ChoosePathB.getType() == "Folder":     # A = Folder  B = Folder
            categories = set()
            if self.chk_pics.isChecked():
                categories.add("images")
            if self.chk_audio.isChecked():
                categories.add("audio")
            if self.chk_vids.isChecked():
                categories.add("video")
            self.folderfolder_win = folderfolder_window(
                self.ChoosePathA.getPath(), self.ChoosePathB.getPath(),
                self.chk_recursive.isChecked(), categories, self, self.cmb_workers.currentData()
            )
            self._show_comparison(self.folderfolder_win)
        elif self.ChoosePathA.getType() == "File" and self.ChoosePathB.getType() == "File":       # A = File    B = File
            self.filefile_win = filefile_window(
                self.ChoosePathA.getPath(), self.ChoosePathB.getPath(), self
            )
            self.filefile_win.pathsChanged.connect(self._update_file_paths)
            self._show_comparison(self.filefile_win)
        elif {self.ChoosePathA.getType(), self.ChoosePathB.getType()} == {"File", "Folder"}:
            side = "A" if self.ChoosePathA.getType() == "File" else "B"
            reference = self.ChoosePathA if side == "A" else self.ChoosePathB
            folder = self.ChoosePathB if side == "A" else self.ChoosePathA
            categories = set()
            if self.chk_pics.isChecked(): categories.add("images")
            if self.chk_audio.isChecked(): categories.add("audio")
            if self.chk_vids.isChecked(): categories.add("video")
            self.filefolder_win = filefolder_window(
                reference.getPath(), folder.getPath(), side,
                self.chk_recursive.isChecked(), categories, self, self.cmb_workers.currentData()
            )
            self.filefolder_win.referenceChanged.connect(
                lambda path, file_side=side: self._update_reference_path(file_side, path)
            )
            self._show_comparison(self.filefolder_win)
        elif {self.ChoosePathA.getType(), self.ChoosePathB.getType()} == {"Folder", "Empty"}:
            selector = self.ChoosePathA if self.ChoosePathA.getType() == "Folder" else self.ChoosePathB
            categories = set()
            if self.chk_pics.isChecked(): categories.add("images")
            if self.chk_audio.isChecked(): categories.add("audio")
            if self.chk_vids.isChecked(): categories.add("video")
            self.duplicates_win = duplicates_window(selector.getPath(), self.chk_recursive.isChecked(), categories, self, self.cmb_workers.currentData())
            self._show_comparison(self.duplicates_win)

    def _show_comparison(self, dialog):
        dialog.finished.connect(self._restore_main)
        self.hide()
        try:
            dialog.show()
        except Exception:
            self._restore_main()
            raise

    def _restore_main(self, result=None):
        self.show()
        self.raise_()
        self.activateWindow()

    def _update_file_paths(self, path_a, path_b):
        for selector, path in ((self.ChoosePathA, path_a), (self.ChoosePathB, path_b)):
            if path:
                selector.loadPath(path)
            else:
                selector.last_file_path = ""
                selector.lbl_path.clear()
                selector.pathChanged.emit()
        self.setOperation()

    def _update_reference_path(self, side, path):
        selector = self.ChoosePathA if side == "A" else self.ChoosePathB
        if path:
            selector.loadPath(path)
        else:
            selector.last_file_path = ""
            selector.lbl_path.clear()
            selector.pathChanged.emit()
        self.setOperation()
