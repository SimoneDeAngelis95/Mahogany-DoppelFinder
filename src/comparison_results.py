"""Reclassify completed comparison results using successful filesystem actions.

No media is decoded here. New destination snapshots are captured by the transfer
worker; unknown destinations stay unverified instead of inheriting trusted data.
"""
from copy import deepcopy
from pathlib import Path

GROUPS = ('common', 'only_a', 'only_b', 'uncertain')

def update_results(result, operation, processed, snapshots, roots, recursive):
    updated = deepcopy(result)
    groups = [g for key in GROUPS for g in updated[key]]
    reference = updated.get('reference')
    internal = not reference and len(set(roots)) == 1
    source_groups = {e['path']: g for g in groups for side in 'AB' for e in g[side]
                     if not reference or e['path'] != reference['path']}
    entries = {e['path']: e for g in groups for side in 'AB' for e in g[side]}
    removed = {source for source, _ in processed} if operation in ('trash', 'move') else set()
    for g in groups:
        for side in 'AB':
            g[side] = [e for e in g[side] if e['path'] not in removed]
    updated['notes'] = [n for n in updated['notes'] if n['path'] not in removed]
    for source, destination in processed:
        if operation == 'trash':
            continue
        group = source_groups.get(source)
        entry = entries.get(source)
        if not group or not entry:
            continue
        for side, root in zip('AB', roots):
            if internal and side == 'B':
                continue
            if reference and side == reference['side']:
                continue
            try:
                relative = Path(destination).relative_to(root)
            except ValueError:
                continue
            if not recursive and len(relative.parts) != 1:
                continue
            if reference and destination == reference['path']:
                continue
            signature = snapshots.get(destination)
            if signature is None:
                updated['notes'].append(dict(path=destination, side=side,
                                            reason='Transferred file could not be verified. Scan again.', uncertain=True))
            elif not any(e['path'] == destination for e in group[side]):
                group[side].append(dict(path=destination, side=side, kind=entry['kind'], signature=signature))
    for key in GROUPS:
        updated[key] = []
    failed = {n['side'] for n in updated['notes'] if n['uncertain']}
    if reference:
        side = 'B' if reference['side'] == 'A' else 'A'
        updated['matches'] = []; updated['different'] = []
        for g in groups:
            if any(e['path'] == reference['path'] for e in g[reference['side']]):
                updated['matches'].extend(g[side])
                if g[side]: updated['common'].append(g)
            else:
                updated['different'].extend(g[side])
                if g[side]: updated['only_a' if side == 'A' else 'only_b'].append(g)
    else:
        for g in groups:
            if internal:
                key = 'common' if len(g['A']) >= 2 else 'only_a'
            elif g['A'] and g['B']:
                key = 'common'
            elif g['A']:
                key = 'uncertain' if 'B' in failed else 'only_a'
            else:
                key = 'uncertain' if 'A' in failed else 'only_b'
            if g['A'] or g['B']:
                updated[key].append(g)
    updated['total'] = sum(len(g['A']) + len(g['B']) for key in GROUPS for g in updated[key]) - (1 if reference and updated['matches'] else 0)
    return updated

def update_reference(result, operation, destination, signature):
    """Keep file/folder classifications when the reference is copied or moved."""
    updated = deepcopy(result)
    reference = updated['reference']
    side = reference['side']; folder_side = 'B' if side == 'A' else 'A'
    if operation == 'copy':
        if signature is not None:
            updated['matches'].append(dict(reference, path=destination, side=folder_side, signature=signature))
        else:
            updated['notes'].append(dict(path=destination, side=folder_side, uncertain=True,
                                        reason='Transferred file could not be verified. Scan again.'))
    else:
        old_path = reference['path']
        reference.update(path=destination, signature=signature)
        for entries in (updated['matches'], updated['different']):
            entries[:] = [e for e in entries if e['path'] != destination]
        updated['notes'] = [n for n in updated['notes'] if n['path'] not in (old_path, destination)]
        updated['notes'].append(dict(path=destination, side=folder_side, uncertain=False,
                                    reason='This is the reference file itself'))
    for key in GROUPS: updated[key] = []
    if updated['matches']:
        group = {'A': [], 'B': []}
        group[side] = [reference]; group[folder_side] = updated['matches']
        updated['common'] = [group]
    for entry in updated['different']:
        group = {'A': [], 'B': []}; group[folder_side] = [entry]
        updated['only_a' if folder_side == 'A' else 'only_b'].append(group)
    return updated
