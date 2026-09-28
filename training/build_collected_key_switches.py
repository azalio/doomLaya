"""Offline mechanism corrections for returning to a key already collected."""
import argparse
import collections
import copy
import hashlib
import json
import re
from pathlib import Path
from training.build_goal_invariant_switches import change_goal


def correction(packet):
    mechanisms = packet.get('targets', {}).get('switch', {})
    match = re.search(r'^Collected keys: (.*)\.', packet['state'], re.M)
    if not match:
        raise ValueError('Missing collected-key observation')
    keys = set(match[1].replace(',', '').split())
    current = packet['observation'].get('execution', {})
    completed = {key for key, value in mechanisms.items()
                 if value.get('route_keys') and set(value['route_keys']) <= keys}
    if not completed:
        return None
    for key, value in mechanisms.items():
        if (value.get('kind') == 'lift' and value.get('phase') in ('board', 'ride')
                and value['distance'] < 5 and current.get('action') == 'use_switch'
                and str(current.get('target_id')) == key):
            return None
    remaining = {key: value for key, value in mechanisms.items() if key not in completed}
    if not remaining:
        return None
    return min(remaining, key=lambda key: (remaining[key]['distance'], key))


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(run, replay, output, fixture):
    if output.exists() or fixture.exists():
        raise ValueError('Output exists')
    if not (run / 'summary.json').exists():
        raise ValueError('Only finalized traces may be used')
    rows = {s: json.loads((replay / (s + '.json')).read_text()) for s in ('train', 'validation')}
    seen = {json.dumps([r['state'], r['question']], sort_keys=True) for group in rows.values() for r in group}
    added = collections.Counter()
    cases = []
    for index, line in enumerate((run / 'decisions.jsonl').open()):
        decision = json.loads(line)
        packet = decision['packet']
        answer = decision['answers'].get('switch')
        if index % 8 or not answer or decision['directive']['action'] != 'use_switch':
            continue
        label = correction(packet)
        if label is None:
            continue
        if label not in packet['questions']['switch']['criteria']:
            raise ValueError('Correction selected an unavailable mechanism')
        row = dict(kind='switch', state=packet['state'], question=copy.deepcopy(packet['questions']['switch']),
                   label=label, category='collected_key_route', source_run=run.name,
                   source_tick=decision['tick'], source_episode=decision['episode'],
                   source_type='offline_collected_key_route_correction', synthetic=False)
        split = 'validation' if decision['tick'] // 140 % 5 == 0 else 'train'
        for variant in [row] + [change_goal(row, key) for key in row['question']['criteria']]:
            identity = json.dumps([variant['state'], variant['question']], sort_keys=True)
            if identity not in seen:
                seen.add(identity)
                rows[split].append(variant)
                added[split] += 1
        if answer['choice'] != label and len(cases) < 12:
            cases.append(dict(source_run=run.name, tick=decision['tick'], check='expected_switch',
                              expected_switch=label, recorded_switch=answer['choice'], packet=packet))
    if not added or not cases:
        raise ValueError('No recorded mechanism corrections found')
    output.mkdir()
    source = run / 'decisions.jsonl'
    manifest = dict(builder_sha256=digest(Path(__file__)), sources={str(source): digest(source),
                    str(replay / 'manifest.json'): digest(replay / 'manifest.json')},
                    added=dict(added), splits={},
                    note='Offline correction of completed-key routes; in-progress nearby lifts are retained. Four-second blocks, every fifth block for validation; goal variants stay together. Same-map development, no runtime rule and no held-out claim.')
    for split, group in rows.items():
        path = output / (split + '.json')
        path.write_text(json.dumps(group, indent=2) + '\n')
        manifest['splits'][split] = dict(rows=len(group), sha256=digest(path),
            categories=dict(collections.Counter(r['category'] for r in group)))
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    fixture.write_text(json.dumps(dict(note=manifest['note'], source_sha256={str(source): digest(source)}, cases=cases), indent=2) + '\n')
    print(json.dumps(dict(added=dict(added), cases=len(cases), splits=manifest['splits']), indent=2))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('run', 'replay', 'output', 'fixture'):
        p.add_argument('--' + name, type=Path, required=True)
    a = p.parse_args()
    build(a.run, a.replay, a.output, a.fixture)
