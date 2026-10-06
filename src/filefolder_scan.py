"""Find a single reference fingerprint in a folder without rescanning its parent."""
import os
from pathlib import Path
import threading
from filesystem_metadata import is_appledouble, APPLEDOUBLE_REASON
from scan_parallel import parallel_records, estimate_cost, MiB

from filefile_window import file_signature
from folder_scan import EXTENSIONS, ScanCancelled, check_cancel, discover, fingerprint, video_properties, prepare_video_properties, filtered_fingerprint, NON_VIDEO


def scan_file_folder(reference, folder, file_side='A', recursive=False, categories=None,
                     cancel=None, progress=None, workers=0, activity=None):
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
    reference_properties = None
    if activity: activity(1, file_side, reference)
    try:
        if Path(reference).suffix.lower() in EXTENSIONS['video']:
            reference_properties = video_properties(reference, cancel)
            if reference_properties == NON_VIDEO: reference_properties = None
        reference_key = None if reference_properties is not None else fingerprint(reference, cancel)
    finally:
        if activity: activity(1, '', '')
    reference_kind = 'video' if reference_properties is not None else reference_key[0]
    category = 'images' if reference_kind in ('image', 'animation') else reference_kind
    if category not in categories:
        raise ValueError('The reference media type is excluded. Enable its filter in the main window.')
    if signature != file_signature(reference):
        raise ValueError('The reference file changed during scanning. Scan again.')
    ref_entry = dict(path=reference, side=file_side, kind=reference_kind, signature=signature)
    notes = []; paths = discover(folder, recursive, folder_side, cancel, notes)
    allowed = EXTENSIONS[category] | {Path(reference).suffix.lower()}
    known = set().union(*EXTENSIONS.values())
    candidates = []
    for path in paths:
        check_cancel(cancel)
        try:
            if os.path.samefile(reference, path):
                notes.append(dict(side=folder_side, path=path, reason='This is the reference file itself', uncertain=False))
            elif is_appledouble(path):
                notes.append(dict(side=folder_side, path=path, reason=APPLEDOUBLE_REASON, uncertain=False))
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
    metadata = prepare_video_properties([(folder_side, path) for path in candidates], cancel, progress, workers, activity) if reference_properties is not None else {}
    fast_paths = {path for path, (_, properties, error) in metadata.items()
                  if properties is not None and properties != NON_VIDEO and not error and properties != reference_properties}
    if reference_properties is not None:
        possible_match = any(path not in fast_paths and not metadata.get(path, (None, None, None))[2] for path in candidates)
        if possible_match:
            if activity: activity(1, file_side, reference)
            try:
                reference_key = fingerprint(reference, cancel)
            finally:
                if activity: activity(1, '', '')
        else:
            reference_key = ('video', ('properties-only', reference_properties))
            ref_entry['properties_only'] = True
    def decode(path, cancel):
        return filtered_fingerprint(path, cancel, metadata, fast_paths, fingerprint)
    records = parallel_records([(folder_side, path) for path in candidates], decode,
                               file_signature, cancel, check_cancel, progress, workers, activity=activity,
                               estimate=lambda path: (MiB, 'other') if path in fast_paths else estimate_cost(path))
    for side, path, before, key, error in records:
        if error:
            notes.append(dict(side=side, path=path, reason=str(error) or type(error).__name__, uncertain=True))
        else:
            entry = dict(path=path, side=side, kind=key[0], signature=before, properties_only=path in fast_paths)
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
