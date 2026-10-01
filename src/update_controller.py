"""Non-blocking Uppie integration; installation means opening the installer."""
from PyQt6.QtCore import QObject, QThreadPool, QTimer
from PyQt6.QtWidgets import QMessageBox, QProgressDialog
from PyQt6.QtCore import Qt
from uppie import Uppie
from filefile_window import _Job
import platform


class UpdateController(QObject):
    def __init__(self, window, version, updater_factory=Uppie):
        super().__init__(window)
        self.window = window
        self.version = version
        self.factory = updater_factory
        self.updater = None
        self.busy = False
        self.progress = None
        self.timer = QTimer(self)
        self.timer.setInterval(150)
        self.timer.timeout.connect(self._progress)
        self.window.destroyed.connect(self.timer.stop)

    def check(self):
        if self.busy: return
        self.busy = True
        def work():
            self.updater = self.factory(repo_owner='SimoneDeAngelis95',
                                        repo_name='Mahogany-DoppelFinder', local_version=self.version)
            # Uppie 1.0 reports network failures as False. An absent release
            # distinguishes those failures from a successful no-update check.
            available = self.updater.is_update_available()
            if not available and self.updater.latest_release is None:
                return 'unavailable'
            return 'available' if available else 'current'
        self.job = _Job(work)
        self.job.signals.done.connect(self._checked)
        QThreadPool.globalInstance().start(self.job)

    def _checked(self, result, error):
        self.busy = False
        if not self.window.isVisible(): return
        if error or result == 'unavailable':
            # Startup network failures should not interrupt normal use.
            return
        if result != 'available': return
        version = self.updater.latest_release.get('tag_name', 'a new version')
        answer = QMessageBox.question(self.window, 'Update available',
            f'{version} is available. Download and open the installer?',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if answer == QMessageBox.StandardButton.Yes: self.download()

    def download(self):
        if self.busy or not self.updater: return
        self.busy = True
        self.updater.progress_percentage = 0
        self.progress = QProgressDialog('Downloading update…', '', 0, 100, self.window)
        self.progress.setCancelButton(None)
        self.progress.setWindowTitle('Mahogany update')
        self.progress.setWindowModality(Qt.WindowModality.NonModal)
        self.progress.setAutoClose(False); self.progress.setAutoReset(False)
        self.progress.setMinimumDuration(0); self.progress.show()
        self.timer.start()
        self.job = _Job(self._download)
        self.job.signals.done.connect(self._downloaded)
        QThreadPool.globalInstance().start(self.job)

    def _download(self):
        # Uppie 1.0 has no public method for downloading the already-approved
        # release. Keep its private API use here, rather than rechecking a
        # potentially different release through update().
        path = self.updater._download_release()
        if not path:
            raise RuntimeError('The update could not be downloaded. Please try again later.')
        return path

    def _progress(self):
        if self.progress:
            value = self.updater.get_progress_percentage()
            self.progress.setRange(0, 100 if value else 0)
            if value: self.progress.setValue(min(99, value))

    def _downloaded(self, path, error):
        self.timer.stop(); self.busy = False
        if self.progress: self.progress.close(); self.progress.deleteLater(); self.progress = None
        if not self.window.isVisible(): return
        if error:
            QMessageBox.warning(self.window, 'Download failed', error); return
        # Opening the installer is quick; keep desktop actions on the UI side.
        try:
            if not self.updater._install_release(path):
                raise RuntimeError(f'The update was downloaded, but its installer could not be opened.\n\n{path}')
        except Exception as exception:
            QMessageBox.warning(self.window, 'Could not open installer', str(exception)); return
        message = ('The downloaded DMG has been opened. Quit Mahogany before replacing the app, '
                   'then install the new version from the DMG.' if platform.system() == 'Darwin' else
                   'The installer has been started. Follow its instructions to install the update.')
        QMessageBox.information(self.window, 'Installer opened', message)
