"""Exclusive file-copy primitive with source validation and partial-copy cleanup."""
import os
from pathlib import Path
import shutil
from filefile_window import file_signature

def copy_without_overwrite(source, destination, expected):
    source, destination = Path(source), Path(destination)
    if source.is_symlink() or file_signature(source) != expected:
        raise ValueError('The source file changed. Scan again.')
    created = False
    try:
        with source.open('rb') as incoming, destination.open('xb') as outgoing:
            created = True
            shutil.copyfileobj(incoming, outgoing, length=1024 * 1024)
            outgoing.flush()
            os.fsync(outgoing.fileno())
        if file_signature(source) != expected:
            raise ValueError('The source file changed during copying.')
        shutil.copystat(source, destination)
    except Exception:
        if created:
            destination.unlink(missing_ok=True)
        raise
    return str(destination)
