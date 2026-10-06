"""Deterministic merge selection and collision-safe destination planning."""
import os
import shutil
from pathlib import Path


def merged_entries(result, shared_side="A"):
    """Keep shared content from the chosen side and all exclusive occurrences."""
    if shared_side not in ("A", "B"):
        raise ValueError("Choose A or B for shared content")
    selected = []
    for group in result['common']:
        selected.extend(group[shared_side])
    for key, side in [('only_a', 'A'), ('only_b', 'B')]:
        for group in result[key]: selected.extend(group[side])
    seen = set(); entries = []
    for entry in selected:
        identity = os.path.realpath(entry['path'])
        if identity not in seen:
            seen.add(identity); entries.append(entry)
    return entries


def validate_merge_target(target, roots):
    target = Path(target).absolute()
    check_destination(target)
    resolved = target.resolve()
    if any(resolved == Path(root).resolve() or Path(root).resolve() in resolved.parents for root in roots):
        raise ValueError('Create folder C outside both source folders and their subfolders.')
    if os.path.lexists(target):
        raise ValueError('Folder C must be new. Choose another name; existing folders are not replaced.')
    if not target.parent.is_dir(): raise ValueError('The destination parent folder is unavailable.')
    return target


def check_destination(path):
    """Reject symlink ancestors, including dangling links, without following them."""
    ancestor = Path(path).parent
    while ancestor != ancestor.parent:
        if ancestor.is_symlink(): raise ValueError('Destination contains a symbolic link')
        ancestor = ancestor.parent


def next_name(path, occupied=(), directories=(), directory=False):
    path = Path(path)
    for number in range(1, 1000000):
        stem = path.name if directory else path.stem
        suffix = '' if directory else path.suffix
        candidate = path.with_name(f'{stem} ({number}){suffix}')
        if not os.path.lexists(candidate) and candidate not in occupied and candidate not in directories:
            return candidate
    raise ValueError('Could not find an available destination name.')


def resolve_plan(requests, policy='skip', occupied=(), directory_mappings=None):
    """Resolve file names and directory/file collisions; reserve all planned paths.

    Returns (plan, skipped, renamed). A plan preserves input order and contains
    (entry, final_destination). Colliding parent directories can be renamed too.
    """
    if policy not in ('skip', 'rename'): raise ValueError('Unsupported conflict policy')
    files = set(occupied); directories = {p for f in files for p in f.parents}
    mappings = directory_mappings if directory_mappings is not None else {}
    plan = []; skipped = []; renamed = []
    for entry, requested in requests:
        requested = Path(requested); check_destination(requested)
        if os.path.abspath(entry['path']) == str(requested.absolute()):
            raise ValueError('Source and destination are the same')
        parts = requested.parts; destination = Path(parts[0]); local = {}; conflict = False
        # Rebuild parents so a directory blocked by a file can be renamed consistently.
        for depth, part in enumerate(parts[1:-1], 1):
            original_parent = Path(*parts[:depth+1])
            proposed = local.get(original_parent, mappings.get(original_parent, destination / part))
            if proposed in files or (os.path.lexists(proposed) and not proposed.is_dir()):
                conflict = True
                if policy == 'skip': break
                proposed = next_name(proposed, files, directories, directory=True)
            if proposed.is_symlink(): raise ValueError('Destination contains a symbolic link')
            local[original_parent] = proposed; destination = proposed
        destination = destination / requested.name
        if conflict and policy == 'skip':
            skipped.append((entry, requested, 'A parent folder name is occupied by a file')); continue
        if os.path.lexists(destination) or destination in files or destination in directories:
            if policy == 'skip':
                skipped.append((entry, requested, 'Destination name already exists')); continue
            destination = next_name(destination, files, directories)
        check_destination(destination)
        files.add(destination); directories.update(destination.parents); mappings.update(local)
        plan.append((entry, destination))
        if destination != requested: renamed.append((entry, requested, destination))
    return plan, skipped, renamed


STOPPED_REASON = 'Not processed: operation stopped by user'


def _space_label(value):
    for unit in ('bytes', 'KiB', 'MiB', 'GiB', 'TiB'):
        if value < 1024 or unit == 'TiB': return f'{value:.1f} {unit}'
        value /= 1024


def check_transfer_space(plan, operation):
    """Estimate copy allocation by volume; same-volume moves need no data copy.

    A 5%/16 MiB margin covers ordinary metadata/allocation overhead. This is
    an early check, not a reservation: other processes may consume disk space.
    """
    if operation not in ('copy', 'move'): return
    volumes = {}
    for entry, destination in plan:
        parent = Path(destination).parent
        while not parent.exists() and parent != parent.parent: parent = parent.parent
        device = parent.stat().st_dev
        if operation == 'move' and device == entry['signature'][0]: continue
        group = volumes.setdefault(device, [parent, 0])
        group[1] += entry['signature'][2]
    for parent, required in volumes.values():
        margin = max(16 * 1024 * 1024, required // 20)
        free = shutil.disk_usage(parent).free
        if required + margin > free:
            raise ValueError(f'Not enough free space on the destination volume ({parent}).\n'
                             f'Estimated requirement including margin: {_space_label(required + margin)}.\n'
                             f'Available: {_space_label(free)}. Nothing was changed.')


def execute_plan(plan, policy, transfer, verify, skipped=(), renamed=(), progress=None, cancel=None):
    """Handle destinations appearing after confirmation without ever overwriting."""
    successes = []; errors = []; skipped = list(skipped)
    final_names = {e['path']: (e, old, new) for e, old, new in renamed}
    reserved = {destination for _, destination in plan}
    runtime_directories = {}
    for index, (entry, destination) in enumerate(plan, 1):
        if cancel is not None and cancel.is_set():
            skipped.extend((e, d, STOPPED_REASON) for e, d in plan[index-1:]); break
        original = destination; reserved.discard(original)
        try:
            verify(entry)
            while True:
                verify(entry)
                current, late_skips, _ = resolve_plan([(entry, destination)], policy, reserved, runtime_directories)
                if late_skips:
                    skipped.extend(late_skips); break
                destination = current[0][1]
                try:
                    check_destination(destination)
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    check_destination(destination)
                    transfer(entry['path'], destination, entry['signature'])
                    successes.append((entry['path'], str(destination)))
                    if destination != original:
                        requested = final_names.get(entry['path'], (entry, original, original))[1]
                        final_names[entry['path']] = (entry, requested, destination)
                    break
                except FileExistsError:
                    if policy == 'skip':
                        skipped.append((entry, destination, 'Destination appeared during the operation')); break
                    # Replan on the next iteration, including parent-folder conflicts.
                    if not os.path.lexists(destination):
                        check_destination(destination)
                        if all(p.is_dir() for p in destination.parents if p.exists()): raise
        except Exception as error: errors.append(entry['path']+': '+str(error))
        finally:
            if progress: progress(index, len(plan))
    successful_sources = {source for source, _ in successes}
    return successes, errors, skipped, [value for source, value in final_names.items() if source in successful_sources]
