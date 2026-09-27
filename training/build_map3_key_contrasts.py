"""Offline resource-count contrasts for the reachable red-key decision."""
import argparse
import collections
import copy
import hashlib
import itertools
import json
import random
import re
from pathlib import Path


def build(source, output):
    if output.exists():
        raise ValueError('Output exists')
    rows = {s: json.loads((source / (s + '.json')).read_text()) for s in ('train', 'validation')}
    keys = [r for r in rows['train'] if r.get('source_run') == 'map03-mechanics-exit-platform54'
            and r['label'] == 'pickup' and 'Reachable items: RedCard#27,' in r['state']]
    if len(keys) != 3:
        raise ValueError('Expected the three recorded red-key approach states')
    holdout_tick = max(r['source_tick'] for r in keys)
    # The base model has seen all three source frames. This is a development
    # contrast split, not unseen-state validation or evidence of generalization.
    rows['train'] = [r for r in rows['train'] if not (r.get('source_run') == 'map03-mechanics-exit-platform54' and r['source_tick'] == holdout_tick)]
    rng = random.Random(9310)
    groups = collections.defaultdict(list)
    for row in rows['train']:
        groups[row['category']].append(row)
    rows['train'] = []
    for category, group in groups.items():
        rng.shuffle(group)
        rows['train'].extend(group if category == 'post_yellow_continue_route' else group[:100])
    for original in keys:
        split = 'validation' if original['source_tick'] == holdout_tick else 'train'
        for hp, shells, bullets, identifier in itertools.product((85, 95, 100, 101), (20, 30, 40, 50), (100, 120, 160, 200), ('27', 'key_25')):
            row = copy.deepcopy(original);state = row['state']
            state, n = re.subn(r'^HP \d+;', f'HP {hp};', state, flags=re.M)
            if n != 1:
                raise ValueError('Missing HP')
            for weapon, count in (('pistol', bullets), ('chaingun', bullets), ('shotgun', shells)):
                state, n = re.subn(rf'\b{weapon} \d+ ammo', f'{weapon} {count} ammo', state)
                if n != 1:
                    raise ValueError('Missing weapon inventory: ' + weapon)
            state = state.replace('RedCard#27', 'RedCard#' + identifier)
            row.update(state=state, category='reachable_red_key_contrast', synthetic=True,
                source_type='counterfactual_map03_resource_counts',
                counterfactual=dict(hp=hp, shells=shells, bullets=bullets, key_identifier=identifier))
            rows[split].append(row)
    seen = {}; splits = {}; removed = collections.Counter(); output.mkdir()
    for split in ('validation', 'train'):
        clean = []
        for row in rows[split]:
            key = json.dumps([row['state'], row['question']], sort_keys=True)
            if key in seen:
                if seen[key] != row['label']:
                    raise ValueError('Conflicting identical input')
                removed[split] += 1
                continue
            seen[key] = row['label']; clean.append(row)
        rng.shuffle(clean);path = output / (split + '.json');path.write_text(json.dumps(clean, indent=2))
        splits[split] = dict(rows=len(clean), sha256=hashlib.sha256(path.read_bytes()).hexdigest(), categories=dict(collections.Counter(r['category'] for r in clean)))
    manifest = dict(note='Synthetic inventory/HP/identifier contrasts around three recorded no-monsters red-key approach states. Geometry, reachability, available choices and pickup label unchanged. HP >=85 and armor=100 do not require the listed healing/armor under the existing offline teacher; shells >=20 and bullets >=100 are above resupply thresholds. Pistol/chaingun shared ammunition remains consistent. Highest source tick held out for development contrasts; all three source frames were seen by the base head, so this is not independent validation. All post-yellow full-ammo corrections retained; old training categories bounded at 100 rows. No runtime rule.', sources={str(source / (s + '.json')): hashlib.sha256((source / (s + '.json')).read_bytes()).hexdigest() for s in ('train', 'validation')}, heldout_source_tick=holdout_tick, splits=splits, removed=dict(removed), builder_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2));print(json.dumps(manifest, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args(); build(args.data, args.output)
