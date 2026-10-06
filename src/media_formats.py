"""One list of supported media extensions for discovery and path selection.

Extensions select candidates; the decoders still validate actual file content.
SVG is excluded because the Pillow comparison pipeline does not render vectors.
"""
EXTENSIONS = {
    'images': frozenset({'.jpg', '.jpeg', '.png', '.gif', '.bmp', '.tiff', '.tif', '.webp', '.apng'}),
    'audio': frozenset({'.mp3', '.mpeg3', '.wav', '.aac', '.flac', '.ogg', '.wma', '.m4a', '.aif', '.aiff', '.opus'}),
    'video': frozenset({'.mp4', '.avi', '.mov', '.mkv', '.flv', '.wmv', '.webm', '.m4v', '.mpeg'}),
}
ALL_EXTENSIONS = frozenset().union(*EXTENSIONS.values())


def file_dialog_filter():
    """Show all supported media by default, then optional category filters."""
    categories = [('Supported media', ALL_EXTENSIONS), ('Images', EXTENSIONS['images']),
                  ('Audio', EXTENSIONS['audio']), ('Videos', EXTENSIONS['video'])]
    return ';;'.join(label+' ('+' '.join('*'+ext for ext in sorted(extensions))+')'
                     for label, extensions in categories)
