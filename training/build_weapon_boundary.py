"""Add offline super-shotgun ammo boundaries while retaining the old weapon set."""
import argparse
import collections
import copy
import hashlib
import itertools
import json
import random
from pathlib import Path

from doomlib.compact_weapon import FORMAT, compact_weapon_input
from doomlib.decision_questions import factorize, with_commitment
from doomlib.policy import request
from training.build_map3_combat import gold


def weapon_label(packet):
    return next(label for kind, label, _ in gold(packet, rapid_fire=True) if kind == 'weapon')


def synthetic(split):
    rng = random.Random(72130 if split == 'train' else 72131)
    bullets = (0, 1, 35, 70) if split == 'train' else (0, 2, 19, 90)
    shells = (0, 1, 2, 3, 8) if split == 'train' else (0, 1, 2, 4, 9)
    distances = (1., 8., 20.) if split == 'train' else (1.5, 7., 15.)
    health = (30, 60, 100) if split == 'train' else (7, 45, 85)
    for index, (shotgun, chaingun, bullet_ammo, shell_ammo, distance) in enumerate(
            itertools.product((False, True), (False, True), bullets, shells, distances)):
        owned = {1, 2, 8} | ({3} if shotgun else set()) | ({4} if chaingun else set())
        inventory = {str(k): dict(owned=int(k in owned),
                     ammo=bullet_ammo if k in (2, 4) else shell_ammo if k in (3, 8) else 0)
                     for k in range(1, 10)}
        state = dict(hp=rng.choice(health), armor=0, inventory=inventory, door=None,
                     keys=[], walls=dict(left=3, right=3),
                     enemies=[dict(id=1, name='DoomImp', distance=distance,
                                   bearing=0, visible=True, x=0, y=0, z=0)], execution={})
        packet = with_commitment(factorize(request(state, {}, None)))
        yield packet, index, 'ssg_ammo_' + str(shell_ammo)


def row_for(packet, **metadata):
    state, question = compact_weapon_input(packet['state'], packet['questions']['weapon'])
    return dict(kind='weapon', state=state, raw_state=packet['state'], question=question,
                label=weapon_label(packet), **metadata)


def build(source, run, output, fixture):
    if output.exists() or fixture.exists():
        raise ValueError('Output exists')
    if not (run / 'summary.json').exists():
        raise ValueError('Source gameplay must be finished')
    paths = [source / (s + '.json') for s in ('train', 'validation')] + [run / 'decisions.jsonl']
    sources = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths}
    rows = {s: json.loads((source / (s + '.json')).read_text()) for s in ('train', 'validation')}
    for split in rows:
        for packet, index, category in synthetic(split):
            rows[split].append(row_for(packet, category=category, source_run='synthetic_ssg_' + split,
                source_tick=index, synthetic=True, source_type='offline_inventory_boundary'))
    errors = []
    for d in map(json.loads, (run / 'decisions.jsonl').open()):
        inventory = d['packet']['observation']['inventory']
        if inventory.get('8', {}).get('owned') and inventory['8']['ammo'] == 1:
            actual = d['answers'].get('weapon', {}).get('choice')
            expected = weapon_label(d['packet'])
            if actual == 'super_shotgun':
                errors.append(d)
            if d['tick'] % 8 == 0:
                split = 'validation' if (d['tick'] // 140) % 5 == 0 else 'train'
                rows[split].append(row_for(d['packet'], category='recorded_ssg_one_shell',
                    source_run=run.name, source_tick=d['tick'], source_episode=d['episode'],
                    source_type='offline_recorded_inventory_boundary', synthetic=False))
    seen = {}
    removed = collections.Counter()
    clean = {}
    for split in ('train', 'validation'):
        clean[split] = []
        for row in rows[split]:
            key = json.dumps([row['state'], row['question']], sort_keys=True)
            if key in seen:
                if seen[key] != row['label']:
                    raise ValueError('Conflicting projected labels')
                removed[split] += 1
                continue
            seen[key] = row['label']
            clean[split].append(row)
    selected = errors[::max(1, len(errors) // 12)][:12]
    if not selected:
        raise ValueError('No recorded underloaded super-shotgun error')
    fixture.write_text(json.dumps(dict(note='Development replay from the source failure; not independent gameplay proof.',
        sources=sources, cases=[dict(source_run=run.name, tick=d['tick'], hp=d['hp'],
            check='expected_weapon', expected_weapon=weapon_label(d['packet']),
            recorded_choice=d['answers']['weapon']['choice'], packet=d['packet']) for d in selected]), indent=2) + '\n')
    output.mkdir()
    manifest = dict(input_projection=FORMAT, sources=sources, removed=dict(removed),
        builder_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        note='Retains existing compact weapon examples and offline rapid-fire priorities. Adds 0/1/2 shell boundaries with distinct state combinations per split. Same-map development, not an unseen map or seed. No runtime fallback.',
        original_error_count=len(errors), splits={})
    for split, data in clean.items():
        path = output / (split + '.json')
        path.write_text(json.dumps(data, indent=2) + '\n')
        manifest['splits'][split] = dict(rows=len(data), sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            categories=dict(collections.Counter(r['category'] for r in data)))
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps(manifest, indent=2))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--data', type=Path, required=True)
    p.add_argument('--run', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--fixture', type=Path, required=True)
    a = p.parse_args()
    build(a.data, a.run, a.output, a.fixture)
