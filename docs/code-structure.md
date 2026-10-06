# Comparison code structure

The comparison interface is shared by folder/folder, file/folder and internal
duplicate searches. Each module has one main responsibility:

| Module                                                     | Responsibility                                                                                                                  |
| ---------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------- |
| `folderfolder_window.py`                                   | Build the interface, populate result trees, manage selection and scan lifecycle.                                                |
| `comparison_previews.py`                                   | Shared preview cards, hover previews, asynchronous decoding and the 32-entry RAM cache.                                         |
| `folder_operations.py`                                     | Select eligible files, validate requests, ask for conflict decisions and confirmation, run approved batches and report results. |
| `folder_actions.py`                                        | Plan destinations, resolve name conflicts, estimate free space and execute transfers without overwriting.                       |
| `file_transfers.py`                                        | Copy one file exclusively, validate its snapshot and clean up an incomplete copy.                                               |
| `comparison_jobs.py`                                       | Qt background scan/action jobs and their progress/completion signals.                                                           |
| `comparison_results.py` | Update and reclassify completed results after successful actions, without decoding media again. |
| `filesystem_metadata.py` | Recognize structurally valid AppleDouble sidecars without excluding real hidden media. |
| `quick_look.py`, `_quick_look_macos.py` | Platform guard and native macOS Quick Look integration. |
| `media_formats.py`                                         | Shared supported extensions and file chooser filters.                                                                           |
| `folder_scan.py`, `filefolder_scan.py`, `scan_parallel.py` | Discover media, compare content and schedule bounded parallel decoding.                                                         |
| `filefolder_window.py`, `duplicates_window.py`             | Specialize the shared interface for reference searches and internal duplicates.                                                 |

`ComparisonPreviews` and `FolderOperations` are behavior mixins used by the result
dialog; they do not introduce extra windows. File/folder and duplicate dialogs
inherit these behaviors from `folderfolder_window` and override their selection,
scan and control rules. Keep constructor argument order and result dictionaries
stable when changing shared code.

`run_folder_action` executes an approved batch without accessing widgets. UI
confirmation stays on the main thread, while work runs through `ActionJob`.
Cancellation takes effect between files. Completed transfers remain in place.
The batch runner returns operation results and whether folder C was created.
The action worker captures destination snapshots and prepares updated comparison
results for the interface.

## Rules to preserve

- Validate source snapshots and matching copies before destructive operations.
- Preserve relative subfolders; never overwrite existing destination files.
- Create C outside A/B, using only verified entries from the completed scan.
- Keep previews in memory and create no thumbnail files.
- Update widgets through Qt signals; block closing while an action is running.
- Update A/B results in memory from successful operations; creating C does not
  change the source scan. **Scan again** detects external changes.

## Validation

Run the `test/test_*.py` scripts with the project's Python environment and
`QT_QPA_PLATFORM=offscreen`, each in a separate Python process. Tests use
temporary media and directories; Trash
and updater interactions are simulated. Native macOS presentation still needs
a manual GUI check.

Patch dependencies in their owning module in tests: folder action dependencies
in `folder_operations`, reference-only actions in `filefolder_window`.
