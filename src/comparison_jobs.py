"""Background jobs and Qt signals for comparison scans and folder actions."""
import threading
from PyQt6.QtCore import QObject, QRunnable, pyqtSignal
from filefile_window import _Job
from folder_scan import ScanCancelled, scan_folders

class ActionSignals(QObject):
    done = pyqtSignal(object, str)
    progress = pyqtSignal(int, int)


class ActionJob(_Job):
    def __init__(self, function):
        super().__init__(lambda: function(self.signals.progress.emit))
        self.signals = ActionSignals()


class ScanSignals(QObject):
    activity = pyqtSignal(int, str, str)
    progress = pyqtSignal(int, int, str)
    done = pyqtSignal(object, str, bool)


class FolderScanJob(QRunnable):
    def __init__(self, roots, recursive, categories, workers=0):
        super().__init__()
        self.roots, self.recursive, self.categories = roots, recursive, categories
        self.workers = workers
        self.cancel = threading.Event()
        self.signals = ScanSignals()

    def run(self):
        try:
            result = scan_folders(*self.roots, self.recursive, self.categories,
                                  self.cancel, self.signals.progress.emit, self.workers, self.signals.activity.emit)
            self.signals.done.emit(result, '', False)
        except ScanCancelled:
            self.signals.done.emit(None, '', True)
        except Exception as error:
            self.signals.done.emit(None, str(error), False)
