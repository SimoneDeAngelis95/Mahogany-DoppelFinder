"""Find a single reference fingerprint in a folder without rescanning its parent."""
import os
from pathlib import Path
import threading
from scan_parallel import parallel_records

from filefile_window import file_signature
from folder_scan import EXTENSIONS, ScanCancelled, check_cancel, discover, fingerprint


def scan_file_folder(reference, folder, file_side='A', recursive=False, categories=None,
                     cancel=None, progress=None, workers=0):
    cancel = cancel or threading.Event()
    progress = progress or (lambda *args: None)
    categories = set(categories if categories is not None else EXTENSIONS)
    if file_side not in ('A', 'B'):
        raise ValueError('Invalid reference side')
    if Path(reference).is_symlink():
        raise ValueError('Choose the original reference file rather than a symbolic link.')
    reference, folder = str(Path(reference).resolve()), str(Path(folder).resolve())
    if not Path(reference).is_file():
        raise ValueError('The reference file is unavailable.')
    if not Path(folder).is_dir():
        raise ValueError('The selected folder is unavailable.')
    if not categories:
        raise ValueError('Select at least one media type.')
    folder_side = 'B' if file_side == 'A' else 'A'
    progress(0, 0, 'Reading the reference file…')
    signature = file_signature(reference)
    reference_key = fingerprint(reference, cancel)
    category = 'images' if reference_key[0] in ('image', 'animation') else reference_key[0]
    if category not in categories:
        raise ValueError('The reference media type is excluded. Enable its filter in the main window.')
    if signature != file_signature(reference):
        raise ValueError('The reference file changed during scanning. Scan again.')
    ref_entry = dict(path=reference, side=file_side, kind=reference_key[0], signature=signature)
    notes = []; paths = discover(folder, recursive, folder_side, cancel, notes)
    allowed = EXTENSIONS[category] | {Path(reference).suffix.lower()}
    known = set().union(*EXTENSIONS.values())
    candidates = []
    for path in paths:
        check_cancel(cancel)
        try:
            if os.path.samefile(reference, path):
                notes.append(dict(side=folder_side, path=path, reason='This is the reference file itself', uncertain=False))
            elif Path(path).suffix.lower() in allowed:
                candidates.append(path)
            else:
                notes.append(dict(side=folder_side, path=path,
                                  reason='Different media type' if Path(path).suffix.lower() in known else 'Unsupported file type',
                                  uncertain=False))
        except OSError as error:
            notes.append(dict(side=folder_side, path=path, reason=str(error), uncertain=True))
    matches, different = [], []
    total = len(candidates)
    records = parallel_records([(folder_side, path) for path in candidates], fingerprint,
                               file_signature, cancel, check_cancel, progress, workers)
    for side, path, before, key, error in records:
        if error:
            notes.append(dict(side=side, path=path, reason=str(error) or type(error).__name__, uncertain=True))
        else:
            entry = dict(path=path, side=side, kind=key[0], signature=before)
            (matches if key == reference_key else different).append(entry)
    check_cancel(cancel)
    if signature != file_signature(reference):
        raise ValueError('The reference file changed during scanning. Results were discarded; scan again.')
    for entries in (matches, different):
        valid = []
        for entry in entries:
            try:
                if file_signature(entry['path']) != entry['signature']: raise ValueError('File changed during scanning')
                valid.append(entry)
            except (OSError, ValueError) as error:
                notes.append(dict(side=folder_side, path=entry['path'], reason=str(error), uncertain=True))
        entries[:] = valid
    result = dict(common=[], only_a=[], only_b=[], uncertain=[], notes=notes,
                  reference=ref_entry, matches=matches, different=different, total=total)
    if matches:
        group = {'A': [], 'B': []}; group[file_side] = [ref_entry]; group[folder_side] = matches
        result['common'].append(group)
    for entry in different:
        group = {'A': [], 'B': []}; group[folder_side] = [entry]
        result['only_a' if folder_side == 'A' else 'only_b'].append(group)
    return result
