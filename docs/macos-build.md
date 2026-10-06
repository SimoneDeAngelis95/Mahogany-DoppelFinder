# Building for macOS

The current `bin/ffmpeg` and `bin/ffprobe` are **arm64** binaries. Build on an
Apple Silicon Mac with an arm64 Python/Qt environment. An Intel build needs
x86_64 versions of both tools and matching Python/Qt dependencies. This setup
does not produce a universal application automatically.

## Prepare and build

From the project root, using the intended build environment:

```sh
python -m pip install setuptools py2app PyQt6 Pillow "uppie==1.0.0" \
  "pyobjc-core==12.2.2" "pyobjc-framework-Cocoa==12.2.2" "pyobjc-framework-Quartz==12.2.2"
python setup_macOS.py py2app
```

Use a normal standalone build for release, not py2app's alias mode. The installed
versions of Python, py2app, Qt and Pillow must be recorded with the release once
the full build has passed validation. Uppie is pinned to 1.0.0 because the update
controller uses its release-download and installer methods.

`setup_macOS.py` reads the app name, author and version from
`src/global_variables.py`; the application and bundle therefore share one
version. It includes:

- The `.icns` application icon and the PNG icons required at runtime.
- FFmpeg and ffprobe under `Contents/Resources/bin`.
- The project license.
- Qt, Pillow, Uppie and Requests, with the required Qt plugin categories.
- PyObjC Cocoa/Quartz for the native macOS Quick Look panel. These modules are
  loaded only on macOS; there is no qlmanage subprocess or debug preview window.

Old icon backups, test media and documentation are not copied as resources.
The script checks that required resources exist, binaries are executable and
FFmpeg/ffprobe match the requested architecture. Qt argv emulation is disabled.
The application uses `RESOURCEPATH` for its main icon and FFmpeg resources.

## Validate the actual bundle

A successful configuration check is not proof that the generated app works.
Before creating a release DMG, open the resulting `.app` from Finder outside
the repository and check:

1. Startup, Dock/Finder icon and all A/B selector icons.
2. Static and animated image previews and comparisons.
3. Audio and video comparisons without relying on a system FFmpeg installation.
4. Subfolder scanning, multi-selection, Trash and conflict handling.
5. Folder C with A and B as the source of shared content.
6. Native Quick Look via Space and right-click, including video playback,
   switching files and closing the panel before closing the comparison window.
7. Automatic update checking and the correct installer asset for this platform.

Create and validate the DMG after the app passes these checks. Signing,
notarization and DMG creation are separate release steps; this setup does not
perform them or publish a GitHub release.

The build environment used for the configuration review did not have setuptools or py2app
installed. The full bundle still needs to be built and tested.

References: [py2app options](https://py2app.readthedocs.io/en/latest/options.html)
and [bundle environment](https://py2app.readthedocs.io/en/latest/environment.html).
