"""Recognize macOS sidecars by their structure, never just their filename."""
from pathlib import Path
import struct


APPLEDOUBLE_REASON = 'macOS metadata (AppleDouble), not a media file'


def is_appledouble(path):
    """Return True only for a structurally valid AppleDouble metadata sidecar."""
    if not Path(path).name.startswith('._'):
        return False
    try:
        with open(path, 'rb') as stream:
            header = stream.read(26)
            if len(header) != 26:
                return False
            magic, version, _, count = struct.unpack('>II16sH', header)
            if magic != 0x00051607 or version not in (0x00010000, 0x00020000) or not count:
                return False
            table = stream.read(count * 12)
            if len(table) != count * 12:
                return False
            stream.seek(0, 2)
            size = stream.tell()
            data_start = 26 + len(table)
            seen = set()
            for entry_id, offset, length in struct.iter_unpack('>III', table):
                # AppleDouble never contains a data fork (entry 1).
                if entry_id in (0, 1) or entry_id in seen:
                    return False
                if offset < data_start or offset + length > size:
                    return False
                seen.add(entry_id)
            return True
    except (OSError, ValueError):
        return False
