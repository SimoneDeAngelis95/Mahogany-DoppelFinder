import platform
import os
from media_formats import EXTENSIONS, ALL_EXTENSIONS

_APP_NAME_ = "Mahogany DoppelFinder"
_VERSION_ = "1.0.0"
_AUTHOR_ = "Simone De Angelis"

# WIDGET CHOSE PATH
_CHOSE_PATH_WIDGET_WIDTH_ = 300
_CHOSE_PATH_WIDGET_HEIGHT_ = 200
_ALLOWED_TYPES_ = ["Folder", "File", "Empty"]

# DEFAULT FOLDER PATH
if platform.system() == 'Darwin' or platform.system() == 'Linux':
    _DEFAULT_FOLDER_PATH_ = os.path.join(os.path.join(os.path.expanduser('~')), 'Desktop')
elif platform.system() == 'Windows':
    _DEFAULT_FOLDER_PATH_ = os.path.join(os.path.join(os.environ['USERPROFILE']), 'Desktop')

# PATHS TO ICONS
_ICON_FOLDER_A_ = "./assets/icon_folder_A.png"
_ICON_FILE_A_   = "./assets/icon_file_A.png"
_ICON_EMPTY_A_   = "./assets/icon_empty_A.png"
_ICON_FOLDER_B_ = "./assets/icon_folder_B.png"
_ICON_FILE_B_   = "./assets/icon_file_B.png"
_ICON_EMPTY_B_   = "./assets/icon_empty_B.png"

# Compatibility names used by the selectors; the format list has one owner.
_IMG_ALLOWED_EXTENSIONS_ = sorted(EXTENSIONS['images'])
_VIDEO_ALLOWED_EXTENSIONS_ = sorted(EXTENSIONS['video'])
_AUDIO_ALLOWED_EXTENSIONS_ = sorted(EXTENSIONS['audio'])
_ALL_ALLOWED_EXTENSIONS_ = sorted(ALL_EXTENSIONS)
