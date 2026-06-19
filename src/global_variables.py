import platform
import os

_APP_NAME_ = "Mahogany DoppelFinder"
_VERSION_ = "1.0.0"
_AUTHOR_ = "Simone De Angelis"

# DEFAULT FOLDER PATH
if platform.system() == 'Darwin' or platform.system() == 'Linux':
    _DEFAULT_FOLDER_PATH_ = os.path.join(os.path.join(os.path.expanduser('~')), 'Desktop')
elif platform.system() == 'Windows':
    _DEFAULT_FOLDER_PATH_ = os.path.join(os.path.join(os.environ['USERPROFILE']), 'Desktop')

# PATHS TO ICONS
_ICON_FOLDER_A_ = "./assets/icon_folder_A.png"
_ICON_FILE_A_   = "./assets/icon_file_A.png"
_ICON_EMPTY_A_   = "./assets/icon_empty_A.jpg"
_ICON_FOLDER_B_ = "./assets/icon_folder_B.png"
_ICON_FILE_B_   = "./assets/icon_file_B.png"
_ICON_EMPTY_B_   = "./assets/icon_empty_B.jpg"

# EXTENSIONS ALLOWED
_IMG_ALLOWED_EXTENSIONS_ = ['.jpg', '.jpeg', '.png', '.gif', '.bmp', '.svg', '.tiff']
_VIDEO_ALLOWED_EXTENSIONS_ = ['.mp4', '.avi', '.mov', '.mkv', '.flv', '.wmv']
_AUDIO_ALLOWED_EXTENSIONS_ = ['.mp3', '.wav', '.aac', '.flac', '.ogg', '.wma']

