"""
Usage:
To create a macOS app bundle using py2app, run the following command in the terminal:
    - pip install py2app
    - python setup_macos.py py2app
    - This will generate a .app bundle in the 'dist' directory.
This script is used to package a Python application into a macOS app bundle using py2app.

This setup works with macOS silicon and intel architectures.
"""

# TODO

from setuptools import setup

APP = ['src/main.py']
DATA_FILES = [
    "assets/icon.icns"
]

OPTIONS = {
    'iconfile': "assets/icon.icns",
    'resources': ["bin", "assets"],                                                    # Include the 'bin' and 'assets' directories in the app bundle
    'argv_emulation': True,
    'plist':{
        'CFBundleName': "Mahogany-DoppelFinder",
        'CFBundleVersion': "V1.0.0",
        'CFBundleShortVersionString': "V1.0.0", 
        'NSHumanReadableCopyright': '© 2026 Made with Love by Simone De Angelis',
        'CFBundleIdentifier': 'com.simonedeamelis.mahoganydoppelfinder',               # Unique identifier for the app
        'LSApplicationCategoryType': 'public.app-category.utilities',                  # Application category
        'NSHighResolutionCapable': True,                                               # Support for high-resolution displays
    },
    'excludes': ['tkinter'],                                                           # Exclude unnecessary modules to reduce app size
    'optimize': 2,                                                                     # Python bytecode optimization level
    # Ensure Qt and PIL modules are collected
    'packages': ['PIL', 'PyQt6'],
    'includes': [
        'PyQt6',
        'PyQt6.QtCore',
        'PyQt6.QtGui',
        'PyQt6.QtWidgets',
        'PyQt6.sip',
    ],
    # Bundle essential Qt plugins (prevents missing platform/imageformat at runtime)
    'qt_plugins': ['platforms', 'styles', 'imageformats', 'iconengines'],
}

setup(
    app=APP,
    data_files=DATA_FILES,
    author="Simone De Angelis",
    copyright="Simone De Angelis",
    description="Mahogany DoppelFinder is a content-based audio comparison tool that compares audio files by their decoded audio data, ignoring container metadata and file format.",
    license="GPLv3",
    options={'py2app': OPTIONS},
    setup_requires=['py2app', 'PyQt6'],
)