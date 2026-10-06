# Comparing and managing folders

During scanning, **Files being processed** shows the current file for each
decoder thread (up to four). Paths are relative to A or B; hover to read the full
path. A free thread shows **Idle**. The panel disappears when scanning finishes.

Before decoding videos, Mahogany compares the container, track counts and the
same video/audio properties used by the exact comparison (including resolution,
frame rates, duration and codecs). A video with no structurally compatible
candidate can be classified without decoding all its frames. Compatible
candidates still receive the full content comparison; internal copies remain
separate occurrences. In file/folder mode, incompatible candidates are skipped
before decoding, and the reference is decoded only when a possible match exists.
Missing or uncertain information falls back to the full comparison. Files are
checked for changes across both phases. This is a duplicate comparison, not a
full video integrity test: structurally excluded videos can contain undetected
frame damage. No video thumbnails or comparison cache are written to disk.

## Result tabs

- **In common:** content present in both A and B. Each group can contain several
  copies on either side; filenames do not establish equality.
- **Only in A / Only in B:** verified content found exclusively on that side.
- **Needs checking:** results that cannot safely be classified. For example,
  unreadable files on the other side can prevent proving a file is exclusive.
- **Not compared:** unsupported, filtered-out or unreadable files and skipped
  links. Check the reason shown for each item.

macOS AppleDouble sidecars (`._…`) are recognized by their file structure and
listed as metadata in **Not compared**. They do not make other results uncertain.
Actual images with the same filename prefix are still compared normally.
Deleting an AppleDouble sidecar leaves the main media file in place but can
remove associated macOS metadata; removing these sidecars is not needed for
comparison.

In **Needs checking**, **Why these results?** explains why uniqueness cannot
be confirmed. **Show Details** lists the responsible paths and scan errors,
including hidden files and inaccessible folders. Reading these details does not
rescan or change any files.

**Show hidden files** is off when opening a result window. It hides dotfiles,
files inside hidden subfolders and files marked hidden by the operating system.
Toggle it to update the lists and tab counts immediately, without rescanning.
This is a display filter: whole-folder actions and folder C still use the full
completed scan. Hidden selections are cleared when the filter is turned off.

Regular files in **Not compared** can be opened or explicitly sent to Trash,
including in a batch. The confirmation warns that no matching copy has been
verified. These entries cannot be copied/moved by comparison actions or included
in C. Links, directories and unavailable files have no deletion action.

**Expand all / Collapse all** opens or closes the groups in the current tab.
The selection counter counts selected file rows, excluding group headings and
hidden rows. Flat result tabs have no group controls.

Select file rows with Cmd-click or Shift-click for batch actions. A group heading
is not a shortcut for deleting its contents. The preview cards and delayed hover
preview help inspect files; double-click opens a file in its default application.

After successful deletions, copies and moves, Mahogany updates the completed
results in memory without scanning the media again. Groups can change tabs as
copies are added or removed; ignored and unprocessed files remain in place.
Use **Scan again** to detect changes made outside Mahogany. The original scan
time remains displayed. No comparison cache is saved to disk.

On macOS, select a file row and press **Space**, or right-click the row and
choose **Quick Look**, to open the native macOS Quick Look panel, including supported video playback.
With exactly one file row selected, **Up / Down** moves through visible file
rows in the current tab and updates the open panel. Group headings, hidden rows
and unavailable files are skipped; collapsed groups remain collapsed. Navigation
stops at the first/last file. With multiple rows selected, it browses only the
selected visible files in list order. Pressing Space to open a multiple selection
starts at its first visible file, regardless of which row is active. Right-click
Quick Look opens the clicked file. The operation selection and current row
stay unchanged; only the file shown in Quick Look advances. Modified arrows
(such as Shift-Up) are not used for preview navigation.
Press Space in the panel to close it; reopening on another file updates the preview. This includes selectable
files in **Not compared**. Group headings have no Quick Look action. The
shortcut and menu are absent on Windows; **Open file** remains available.
Mahogany creates no preview files; macOS manages its own Quick Look caches.

## Copy and move destinations

Paths are preserved relative to the source root:

```text
A/trips/portrait.jpg  →  B/trips/portrait.jpg
```

The location of an existing matching copy does not change this destination.
If B already contains the same content at `B/archive/photo.jpg`, moving the file
above still places it at `B/trips/portrait.jpg`.

Existing destination files are never overwritten. When names conflict, choose
**Rename automatically** or **Ignore conflicting files** for the batch. Automatic
renaming adds a numbered suffix; a conflicting parent-folder name can be renamed
as well. Ignoring a conflict leaves that source file untouched. New conflicts
that appear during execution use the same choice.

Sources are checked again before operations. If a source or a protected matching
copy changes, Mahogany reports the problem instead of trusting the old scan.
Capacity checks estimate the free space needed; they do not reserve disk space.
A batch can finish partly if an error occurs or you stop it. Review the result
and “Show Details”; there is no automatic rollback of completed operations.

## Whole-folder actions

**Folder A actions** and **Folder B actions** use the completed scan, not the
current tab or selection. Their media dropdown can restrict them to images,
audio or video. Matching-file removal protects checked copies on the opposite
side. Exclusive-file copy/move excludes unverified results.

In **Folder / No comparison**, removing extra duplicates keeps one checked copy
per content group. Selecting every copy in a group is rejected.

## Creating folder C

Choose a location (the chooser starts at the Desktop), a new folder name and
whether to keep **copies from A** or **copies from B** for shared content.
C must be new and outside both source folders. It contains:

1. Every occurrence of content exclusive to A.
2. Every occurrence of content exclusive to B.
3. Every occurrence on the chosen side of content shared by A and B.

For example, two copies in A and one matching copy in B produce two copies in C
when A is chosen, or one when B is chosen. Internal duplicates are deliberately
preserved, together with their relative paths and names. C is a combination of
the archives, not a globally deduplicated archive.

C uses every media category included in the completed scan. The media dropdown
beside the A/B actions does not limit C. Unverified and not-compared entries,
unsupported documents and empty directories are not exported. Name conflicts
between files coming from the two sources use the usual rename/ignore choices.
A and B are never moved or deleted when creating C.

## What counts as identical?

Static images are compared using normalized decoded pixels and dimensions.
Animations also compare frame sequence, duration and looping behavior.
Audio and video use decoded content plus relevant stream/container properties.
Different names or ordinary metadata do not determine equality, but different
compression results, codecs, timing or container properties can matter.
Mahogany does not perform perceptual similarity matching.

Previews use a 32-entry in-memory cache. They create no thumbnail files.
