"""Retain the mechanism dataset and add observations from an audited teacher replay."""
import argparse
import collections
import copy
import hashlib
import json
from pathlib import Path


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(source, probe_path, output):
    if output.exists():
        raise ValueError('Output exists')
    probe = json.loads(probe_path.read_text())
    if not probe.get('completed'):
        raise ValueError('Teacher API replay was not completed')
    rows = {split: json.loads((source / (split + '.json')).read_text()) for split in ('train', 'validation')}
    identity = lambda row: json.dumps([row['state'], row['question']], sort_keys=True)
    seen = {identity(row): row['label'] for group in rows.values() for row in group}
    added, duplicates = collections.Counter(), collections.Counter()
    for case in probe['results']:
        if 'switch' not in case['expected']:
            continue
        row = dict(kind='switch', state=case['packet']['state'],
                   question=copy.deepcopy(case['packet']['questions']['switch']),
                   label=case['expected']['switch'], category='successful_teacher_mechanism',
                   source_run=Path(probe['source_run']).name, source_tick=case['tick'],
                   source_episode=case['episode'], source_type='offline_teacher_api_replay', synthetic=False)
        key = identity(row)
        if key in seen:
            if seen[key] != row['label']:
                raise ValueError('Conflicting teacher label at tick ' + str(case['tick']))
            duplicates['teacher'] += 1
            continue
        seen[key] = row['label']
        split = 'validation' if case['tick'] // 700 % 5 == 0 else 'train'
        rows[split].append(row)
        added[split] += 1
    output.mkdir()
    manifest = dict(input_projection='full-switch-observations-v1', sources={
        str(probe_path): digest(probe_path), str(source / 'train.json'): digest(source / 'train.json'),
        str(source / 'validation.json'): digest(source / 'validation.json')},
        added=dict(added), duplicates=dict(duplicates), splits={},
        builder_sha256=digest(Path(__file__)),
        note='Original splits and labels retained. New teacher observations use every fifth 20-second block for validation. Same-map development, no held-out map or seed claim. IDs remain in frozen text but are excluded from numeric features.')
    for split, group in rows.items():
        path = output / (split + '.json')
        path.write_text(json.dumps(group, indent=2) + '\n')
        manifest['splits'][split] = dict(rows=len(group), sha256=digest(path))
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps(manifest, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', type=Path, required=True)
    parser.add_argument('--probe', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    build(args.data, args.probe, args.output)
