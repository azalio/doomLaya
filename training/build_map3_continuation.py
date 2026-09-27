"""Offline command corrections from later MAP03 states, with previous-data replay."""
import argparse
import collections
import copy
import hashlib
import json
import random
from pathlib import Path

from training.build_map3_resources import labels


def build(run, replay, output):
    if output.exists():
        raise ValueError('Output exists')
    path = run / 'decisions.jsonl'
    pools = {'train': collections.defaultdict(list), 'validation': collections.defaultdict(list)}
    for decision in map(json.loads, path.read_text().splitlines()):
        packet = decision['packet']
        state = '\n'.join(line for line in packet['state'].splitlines() if not line.startswith('Current command:'))
        later = 'Collected keys: blue, yellow.' in state
        # There is only one post-yellow attempt. Hold out complete 20-second
        # blocks for development evaluation; this is not an independent run.
        split = ('validation' if int(decision['game_seconds']) // 20 % 4 == 0 else 'train') if later else ('validation' if decision['episode'] % 3 == 0 else 'train')
        for kind, label, category in labels(packet):
            if kind != 'command':
                continue
            if later and category == 'continue_route':
                category = 'post_yellow_continue_route'
            pools[split][category].append(dict(kind=kind, label=label, category=category,
                state=state, question=copy.deepcopy(packet['questions'][kind]), source_run=run.name,
                source_tick=decision['tick'], source_episode=decision['episode'],
                source_type='offline_map03_resource_correction', synthetic=False))
    rng = random.Random(9307)
    rows = {}
    sources = {str(path): hashlib.sha256(path.read_bytes()).hexdigest()}
    for split, groups in pools.items():
        fresh = []
        for group in groups.values():
            rng.shuffle(group)
            fresh.extend(group[:220 if split == 'train' else 70])
        old_path = replay / (split + '.json')
        sources[str(old_path)] = hashlib.sha256(old_path.read_bytes()).hexdigest()
        old = json.loads(old_path.read_text())
        if any(row['kind'] != 'command' for row in old):
            raise ValueError('Command-only replay required')
        rows[split] = fresh + old
    seen = {}
    removed = collections.Counter()
    output.mkdir()
    splits = {}
    # Check validation first: no source input held out above can enter training.
    for split in ('validation', 'train'):
        clean = []
        for row in rows[split]:
            key = json.dumps([row['state'], row['question']], sort_keys=True)
            if key in seen:
                if seen[key] != row['label']:
                    raise ValueError('Conflicting labels for identical input')
                removed[split] += 1
                continue
            seen[key] = row['label']
            clean.append(row)
        rng.shuffle(clean)
        dest = output / (split + '.json')
        dest.write_text(json.dumps(clean, indent=2))
        splits[split] = dict(rows=len(clean), sha256=hashlib.sha256(dest.read_bytes()).hexdigest(), categories=dict(collections.Counter(row['category'] for row in clean)))
    manifest = dict(note='Recorded model states labeled offline with build_map3_resources.labels; controller unchanged. Only Current command line removed, matching server projection. All previous replay rows retained unless duplicate. Existing episode-modulo split before yellow; after yellow, 20-second blocks with floor(seconds/20)%4==0 held out. Nearby states share one attempt: development fitting, not independent generalization.', sources=sources, splits=splits, removed=dict(removed), builder_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2))
    print(json.dumps(manifest, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run', type=Path)
    parser.add_argument('--replay', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    build(args.run, args.replay, args.output)
