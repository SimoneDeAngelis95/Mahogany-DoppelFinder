"""Open/reveal files with visible errors and no terminal-only subprocess failures."""
from pathlib import Path
import sys
from PyQt6.QtCore import QProcess, QUrl
from PyQt6.QtGui import QDesktopServices
from PyQt6.QtWidgets import QMessageBox


def available_file(owner, path):
    if path and Path(path).is_file():
        return True
    QMessageBox.warning(owner, 'File no longer available',
                        'The file is no longer at its original location. It may have been '
                        'renamed, moved or deleted outside Mahogany. Select it again or scan again.'
                        + (f'\n\n{path}' if path else ''))
    return False


def open_file(owner, path):
    if not available_file(owner, path):
        return False
    if not QDesktopServices.openUrl(QUrl.fromLocalFile(path)):
        QMessageBox.warning(owner, 'Could not open file', 'No application could open the selected file.')
        return False
    return True


def reveal_file(owner, path):
    if not available_file(owner, path):
        return False
    if sys.platform != 'darwin':
        if not QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(path).parent))):
            QMessageBox.warning(owner, 'Could not show file', 'Could not open the containing folder.')
            return False
        return True
    process = QProcess(owner)
    process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
    reported = False

    def report(detail):
        nonlocal reported
        if reported:
            return
        reported = True
        message = QMessageBox(owner)
        message.setWindowTitle('Could not show file')
        message.setIcon(QMessageBox.Icon.Warning)
        message.setText('Finder could not show the selected file.')
        message.setInformativeText('The file may have been renamed, moved or become unavailable.')
        message.setDetailedText(f'{path}\n\n{detail}')
        message.exec()

    def finished(code, status):
        if code or status != QProcess.ExitStatus.NormalExit:
            report(bytes(process.readAllStandardOutput()).decode('utf-8', errors='replace').strip()
                   or process.errorString())
        process.deleteLater()

    def failed(error):
        report(process.errorString())
        if error == QProcess.ProcessError.FailedToStart:
            process.deleteLater()

    process.finished.connect(finished)
    process.errorOccurred.connect(failed)
    process.start('open', ['-R', path])
    return True
