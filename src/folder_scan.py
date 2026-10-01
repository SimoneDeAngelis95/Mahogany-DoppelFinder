"""Linear content-fingerprint scan using the same rules as the two-file comparers."""
from collections import defaultdict
import hashlib
import json
import os
from pathlib import Path
import threading

from PIL import Image
from scan_parallel import parallel_records
from filefile_window import file_kind, file_signature
from comparers.StaticImageComparer import StaticImageComparer
from comparers.MultiFrameImageComparer import MultiFrameImageComparer
from FFmpegAdapter import FFmpegAdapter

EXTENSIONS = {
    'images': {'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.tif', '.webp', '.apng', '.svg'},
    'audio': {'.mp3', '.wav', '.aac', '.flac', '.ogg', '.wma', '.m4a', '.aif', '.aiff', '.opus'},
    'video': {'.mp4', '.avi', '.mov', '.mkv', '.flv', '.wmv', '.webm', '.m4v'},
}
AUDIO_PROPERTIES = ('codec_name', 'bit_depth', 'sample_rate', 'channels', 'channel_layout')
VIDEO_PROPERTIES = ('codec_name', 'profile', 'width', 'height', 'pixel_format', 'bit_depth',
                    'time_base', 'real_frame_rate', 'average_frame_rate', 'start_time', 'duration', 'frame_count')
VIDEO_AUDIO_PROPERTIES = AUDIO_PROPERTIES + ('time_base', 'start_time', 'duration')


class ScanCancelled(Exception):
    pass


def check_cancel(cancel):
    if cancel.is_set():
        raise ScanCancelled()


def fingerprint(path, cancel):
    check_cancel(cancel)
    kind = file_kind(path)
    if kind == 'image':
        digest, size = StaticImageComparer().image_to_sha256(path)
        return kind, size, digest
    if kind == 'animation':
        with Image.open(path) as image:
            frames, loop = image.n_frames, image.info.get('loop')
        digest = MultiFrameImageComparer().image_to_sha256(path)
        check_cancel(cancel)
        return kind, frames, loop, digest
    adapter = FFmpegAdapter()
    if kind == 'audio':
        info = adapter.get_audio_info(path)
        key = tuple(info.get(p) for p in ('format_name',) + AUDIO_PROPERTIES)
        digest = adapter.get_audio_sha256(path)
        check_cancel(cancel)
        return kind, key, digest
    media = adapter.get_media_info(path)
    parts = [('container', media['format_name'], media['audio_stream_count'], media['video_stream_count'])]
    for index in range(media['audio_stream_count']):
        check_cancel(cancel)
        info = adapter.get_audio_info(path, index)
        parts.append(('audio', tuple(info.get(p) for p in VIDEO_AUDIO_PROPERTIES),
                      adapter.get_audio_sha256(path, index)))
    for index in range(media['video_stream_count']):
        check_cancel(cancel)
        info = adapter.get_video_info(path, index)
        digest = hashlib.sha256()
        frames = adapter.iter_video_framehash(path, index)
        try:
            for frame in frames:
                check_cancel(cancel)
                digest.update(json.dumps(frame, sort_keys=True, separators=(',', ':')).encode())
                digest.update(b'\n')
        finally:
            frames.close()
        parts.append(('video', tuple(info.get(p) for p in VIDEO_PROPERTIES), digest.hexdigest()))
    return kind, tuple(parts)


def discover(root, recursive, side, cancel, report):
    """Do not follow directory symlinks or leave the selected root."""
    paths = []
    def visit(directory):
        check_cancel(cancel)
        try:
            with os.scandir(directory) as entries:
                for entry in entries:
                    check_cancel(cancel)
                    try:
                        if entry.is_symlink():
                            report.append(dict(side=side, path=entry.path, reason='Symbolic link skipped', uncertain=False))
                        elif entry.is_file(follow_symlinks=False):
                            paths.append(entry.path)
                        elif recursive and entry.is_dir(follow_symlinks=False):
                            visit(entry.path)
                    except OSError as error:
                        report.append(dict(side=side, path=entry.path, reason=str(error), uncertain=True))
        except OSError as error:
            report.append(dict(side=side, path=str(directory), reason=str(error), uncertain=True))
    visit(root)
    return sorted(paths)


def scan_folders(root_a, root_b=None, recursive=False, categories=None, cancel=None, progress=None, workers=0):
    cancel = cancel or threading.Event()
    progress = progress or (lambda *args: None)
    categories = set(categories if categories is not None else EXTENSIONS)
    if not categories:
        raise ValueError('Select at least one media type.')
    internal = root_b is None
    roots = [str(Path(p).resolve()) for p in ((root_a,) if internal else (root_a, root_b))]
    for root in roots:
        if not Path(root).is_dir():
            raise ValueError('One of the selected folders is unavailable.')
    if not internal and os.path.samefile(*roots):
        raise ValueError('Select two different folders.')
    notes = []
    progress(0, 0, 'Discovering files…')
    paths = [discover(root, recursive, 'AB'[i], cancel, notes) for i, root in enumerate(roots)]
    allowed = set().union(*(EXTENSIONS[c] for c in categories))
    known = set().union(*EXTENSIONS.values())
    candidates = []
    for index, files in enumerate(paths):
        for path in files:
            extension = Path(path).suffix.lower()
            if extension in allowed:
                candidates.append(('AB'[index], path))
            else:
                notes.append(dict(side='AB'[index], path=path,
                                  reason='Excluded by media filter' if extension in known else 'Unsupported file type',
                                  uncertain=False))
    groups = defaultdict(lambda: {'A': [], 'B': []})
    total = len(candidates)
    records = parallel_records(candidates, fingerprint, file_signature, cancel,
                               check_cancel, progress, workers)
    for side, path, signature, key, error in records:
        if error:
            notes.append(dict(side=side, path=path, reason=str(error) or type(error).__name__, uncertain=True))
            continue
        selected_category = 'images' if key[0] in ('image', 'animation') else key[0]
        if selected_category not in categories:
            notes.append(dict(side=side, path=path, reason='Excluded by detected media type', uncertain=False))
            continue
        groups[key][side].append(dict(path=path, side=side, kind=key[0], signature=signature))
    check_cancel(cancel)
    # Recheck all entries: an early file may have changed while later files decoded.
    for group in groups.values():
        for side in ('A', 'B'):
            valid = []
            for entry in group[side]:
                try:
                    if file_signature(entry['path']) != entry['signature']:
                        raise ValueError('File changed during scanning')
                    valid.append(entry)
                except (OSError, ValueError) as error:
                    notes.append(dict(side=side, path=entry['path'], reason=str(error), uncertain=True))
            group[side] = valid
    failed = {side for side in ('A', 'B') if any(n['side'] == side and n['uncertain'] for n in notes)}
    result = dict(common=[], only_a=[], only_b=[], uncertain=[], notes=notes, roots=roots, total=total)
    for group in groups.values():
        if internal:
            if len(group['A']) >= 2:
                result['common'].append(group)
            elif group['A']:
                result['only_a'].append(group)
        elif group['A'] and group['B']:
            result['common'].append(group)
        elif group['A']:
            result['uncertain' if 'B' in failed else 'only_a'].append(group)
        elif group['B']:
            result['uncertain' if 'A' in failed else 'only_b'].append(group)
    return result
