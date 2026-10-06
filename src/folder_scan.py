"""Linear content-fingerprint scan using the same rules as the two-file comparers."""
from collections import Counter, defaultdict
import hashlib
import json
import os
from pathlib import Path
import threading

from PIL import Image
from scan_parallel import parallel_records, estimate_cost, MiB
from filefile_window import file_kind, file_signature
from comparers.StaticImageComparer import StaticImageComparer
from comparers.MultiFrameImageComparer import MultiFrameImageComparer
from FFmpegAdapter import FFmpegAdapter

from media_formats import EXTENSIONS
from filesystem_metadata import is_appledouble, APPLEDOUBLE_REASON

AUDIO_PROPERTIES = ('codec_name', 'bit_depth', 'sample_rate', 'channels', 'channel_layout')
VIDEO_PROPERTIES = ('codec_name', 'profile', 'width', 'height', 'pixel_format', 'bit_depth',
                    'time_base', 'real_frame_rate', 'average_frame_rate', 'start_time', 'duration', 'frame_count')
VIDEO_AUDIO_PROPERTIES = AUDIO_PROPERTIES + ('time_base', 'start_time', 'duration')
NON_VIDEO = ('not-video',)


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


def video_properties(path, cancel):
    """Read only discriminants already required by the exact video comparison.

    Missing/invalid information falls back to full decoding. This proves whether
    videos can match, not whether every frame in the file is decodable.
    """
    check_cancel(cancel)
    try:
        with Image.open(path):
            return NON_VIDEO
    except (OSError, ValueError):
        pass
    adapter = FFmpegAdapter()
    try:
        media = adapter.get_media_info(path)
        if not media['video_stream_count']:
            return NON_VIDEO
        if not media['format_name']:
            return None
        if set(media['format_name'].split(',')) & {'image2', 'image2pipe', 'jpeg_pipe',
                'png_pipe', 'bmp_pipe', 'tiff_pipe', 'webp_pipe', 'gif', 'apng'}:
            return NON_VIDEO
        parts = [('container', media['format_name'], media['audio_stream_count'], media['video_stream_count'])]
        for index in range(media['audio_stream_count']):
            check_cancel(cancel)
            info = adapter.get_audio_info(path, index)
            parts.append(('audio', tuple(info.get(p) for p in VIDEO_AUDIO_PROPERTIES)))
        for index in range(media['video_stream_count']):
            check_cancel(cancel)
            info = adapter.get_video_info(path, index)
            if any(info.get(p) is None for p in ('codec_name', 'width', 'height',
                    'pixel_format', 'time_base', 'duration', 'real_frame_rate', 'average_frame_rate')):
                return None
            parts.append(('video', tuple(info.get(p) for p in VIDEO_PROPERTIES)))
        check_cancel(cancel)
        return tuple(parts)
    except ScanCancelled:
        raise
    except Exception:
        return None


def prepare_video_properties(candidates, cancel, progress, workers, activity):
    if not any(Path(path).suffix.lower() in EXTENSIONS['video'] for _, path in candidates):
        return {}
    records = parallel_records(candidates, video_properties, file_signature, cancel,
        check_cancel, lambda n, total, text: progress(n, total, 'Reading video properties · '+text),
        workers, activity=activity, estimate=lambda path: (16 * MiB, 'other'))
    return {path: (signature, key, error) for _, path, signature, key, error in records}


def filtered_fingerprint(path, cancel, metadata, fast_paths, decode):
    """Only skip decoding when a known structural mismatch proves uniqueness."""
    if path in metadata:
        before, properties, error = metadata[path]
        if error: raise error
        if file_signature(path) != before:
            raise ValueError('File changed after reading video properties')
        if path in fast_paths:
            return 'video', ('properties-only', properties)
    return decode(path, cancel)


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


def scan_folders(root_a, root_b=None, recursive=False, categories=None, cancel=None, progress=None, workers=0, activity=None):
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
            check_cancel(cancel)
            if is_appledouble(path):
                notes.append(dict(side='AB'[index], path=path,
                                  reason=APPLEDOUBLE_REASON, uncertain=False))
                continue
            extension = Path(path).suffix.lower()
            if extension in allowed:
                candidates.append(('AB'[index], path))
            else:
                notes.append(dict(side='AB'[index], path=path,
                                  reason='Excluded by media filter' if extension in known else 'Unsupported file type',
                                  uncertain=False))
    groups = defaultdict(lambda: {'A': [], 'B': []})
    total = len(candidates)
    metadata = prepare_video_properties(candidates, cancel, progress, workers, activity)
    counts = Counter(properties for _, properties, error in metadata.values() if properties is not None and properties != NON_VIDEO and not error)
    unknown = any(properties is None and not error for _, properties, error in metadata.values())
    fast_paths = {path for path, (_, properties, error) in metadata.items()
                  if not unknown and properties is not None and properties != NON_VIDEO and not error and counts[properties] == 1}
    def decode(path, cancel):
        return filtered_fingerprint(path, cancel, metadata, fast_paths, fingerprint)
    records = parallel_records(candidates, decode, file_signature, cancel,
                               check_cancel, progress, workers, activity=activity,
                               estimate=lambda path: (MiB, 'other') if path in fast_paths else estimate_cost(path))
    for side, path, signature, key, error in records:
        if error:
            notes.append(dict(side=side, path=path, reason=str(error) or type(error).__name__, uncertain=True))
            continue
        selected_category = 'images' if key[0] in ('image', 'animation') else key[0]
        if selected_category not in categories:
            notes.append(dict(side=side, path=path, reason='Excluded by detected media type', uncertain=False))
            continue
        groups[key][side].append(dict(path=path, side=side, kind=key[0], signature=signature, properties_only=path in fast_paths))
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
