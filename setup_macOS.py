"""Build a standalone macOS app: python setup_macOS.py py2app.

Install py2app and the runtime dependencies first (see docs/macos-build.md).
The bundle architecture follows the build machine; FFmpeg must match it.
"""
import ast
import os
from pathlib import Path
import platform
import sys
import subprocess

from setuptools import setup

ROOT = Path(__file__).resolve().parent


def app_metadata():
    """Read release metadata without importing Qt or application modules."""
    wanted = {'_APP_NAME_', '_VERSION_', '_AUTHOR_'}
    values = {}
    source = (ROOT / 'src' / 'global_variables.py').read_text()
    for node in ast.parse(source).body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name) and target.id in wanted:
                    values[target.id] = ast.literal_eval(node.value)
    if wanted != values.keys():
        raise ValueError('Application release metadata is incomplete.')
    return values


def build_configuration():
    metadata = app_metadata()
    assets = sorted(str(path) for path in (ROOT / 'assets').glob('icon*.png'))
    binaries = [ROOT / 'bin' / name for name in ('ffmpeg', 'ffprobe')]
    icon = ROOT / 'assets' / 'icon.icns'
    required = [icon, ROOT / 'assets' / 'icon.png', ROOT / 'LICENSE', *binaries]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise FileNotFoundError('Missing bundle resources: '+', '.join(missing))
    if any(not os.access(path, os.X_OK) for path in binaries):
        raise ValueError('Bundled ffmpeg and ffprobe must be executable.')
    architecture = platform.machine()
    if architecture not in ('arm64', 'x86_64'):
        raise ValueError('Build on an Apple Silicon or Intel Mac.')
    for binary in binaries:
        architectures = subprocess.check_output(
            ['/usr/bin/lipo', '-archs', str(binary)], text=True).split()
        if architecture not in architectures:
            raise ValueError(f'{binary.name} does not support {architecture}. Replace it before building.')
    options = {
        'iconfile': str(icon),
        'argv_emulation': False,  # GUI toolkits handle their own event loop.
        'arch': architecture,
        'optimize': 2,
        'excludes': ['tkinter', 'PyObjCTest'],
        'packages': ['PIL', 'PyQt6', 'uppie', 'requests', 'objc', 'Foundation', 'AppKit', 'Quartz'],
        'includes': ['PyQt6.QtCore', 'PyQt6.QtGui', 'PyQt6.QtWidgets', 'PyQt6.sip', '_quick_look_macos'],
        'qt_plugins': ['platforms', 'styles', 'imageformats', 'iconengines'],
        'plist': {
            'CFBundleName': metadata['_APP_NAME_'],
            'CFBundleDisplayName': metadata['_APP_NAME_'],
            'CFBundleVersion': metadata['_VERSION_'],
            'CFBundleShortVersionString': metadata['_VERSION_'],
            'CFBundleIdentifier': 'com.simonedeamelis.mahoganydoppelfinder',
            'NSHumanReadableCopyright': '© 2026 '+metadata['_AUTHOR_'],
            'LSApplicationCategoryType': 'public.app-category.utilities',
            'NSHighResolutionCapable': True,
        },
    }
    return {
        'name': 'Mahogany-DoppelFinder',
        'version': metadata['_VERSION_'],
        'app': [str(ROOT / 'src' / 'main.py')],
        'py_modules': [],  # Avoid setuptools auto-discovering test/assets folders.
        'data_files': [('assets', assets), ('bin', [str(path) for path in binaries]),
                       ('', [str(ROOT / 'LICENSE')])],
        'author': metadata['_AUTHOR_'],
        'description': 'Content-based image, animation, audio and video comparison.',
        'license': 'GPLv3',
        'options': {'py2app': options},
        'install_requires': ['PyQt6>=6.6', 'Pillow>=10', 'uppie==1.0.0',
                             "pyobjc-core==12.2.2; sys_platform == 'darwin'",
                             "pyobjc-framework-Cocoa==12.2.2; sys_platform == 'darwin'",
                             "pyobjc-framework-Quartz==12.2.2; sys_platform == 'darwin'"],
    }


if __name__ == '__main__':
    if sys.platform != 'darwin':
        raise SystemExit('This build script is for macOS.')
    # Make sibling application modules visible to py2app dependency analysis.
    sys.path.insert(0, str(ROOT / 'src'))
    setup(**build_configuration())
