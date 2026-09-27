"""Offline action labels from a completed mechanics route, with gameplay replay."""
import argparse
import collections
import copy
import hashlib
import json
import random
from pathlib import Path


def build(run, replay, output):
    if output.exists():
        raise ValueError('Output exists')
    summary = json.loads((run / 'summary.json').read_text())
    if not summary.get('map_completed') or not summary.get('no_monsters'):
        raise ValueError('A completed no-monsters mechanics fixture is required')
    sources = {str(run / name): hashlib.sha256((run / name).read_bytes()).hexdigest()
               for name in ('config.json', 'summary.json', 'examples.jsonl')}
    pools = {'train': [], 'validation': []}
    for original in map(json.loads, (run / 'examples.jsonl').read_text().splitlines()):
        if original['kind'] != 'command':
            continue
        row = copy.deepcopy(original)
        row['state'] = '\n'.join(line for line in row['state'].splitlines()
                                 if not line.startswith('Current command:'))
        row['category'] = 'mechanics_route_' + row['label']
        split = 'validation' if row['source_tick'] // 140 % 5 == 0 else 'train'
        pools[split].append(row)
    rng = random.Random(9308)
    for split in pools:
        path = replay / (split + '.json')
        sources[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
        groups = collections.defaultdict(list)
        for row in json.loads(path.read_text()):
            if row['kind'] != 'command':
                raise ValueError('Command-only replay required')
            groups[row['category']].append(row)
        for category, rows in groups.items():
            rng.shuffle(rows)
            # Keep the whole new full-inventory correction; bound older, large
            # categories so route demonstrations receive enough training weight.
            limit = len(rows) if split == 'validation' or category == 'post_yellow_continue_route' else 160
            pools[split].extend(rows[:limit])
    seen = {}; removed = collections.Counter(); splits = {}
    output.mkdir()
    for split in ('validation', 'train'):
        clean = []
        for row in pools[split]:
            key = json.dumps([row['state'], row['question']], sort_keys=True)
            if key in seen:
                if seen[key] != row['label']:
                    raise ValueError('Conflicting labels for identical input')
                removed[split] += 1
                continue
            seen[key] = row['label']; clean.append(row)
        rng.shuffle(clean)
        path = output / (split + '.json'); path.write_text(json.dumps(clean, indent=2))
        splits[split] = dict(rows=len(clean), sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
                            categories=dict(collections.Counter(r['category'] for r in clean)))
    manifest = dict(note='Supervised command labels from a successful no-monsters MAP03 mechanics demonstration, never live gameplay by Laya. Every fifth four-second demonstration block is held out; nearby states are correlated. Previous gameplay-derived replay retains its allocation, with at most 160 training rows per old category and every post-yellow full-inventory correction. Only Current command line removed, matching server projection. Development fitting, not independent generalization.', sources=sources, splits=splits, removed=dict(removed), builder_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2))
    print(json.dumps(manifest, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run', type=Path)
    parser.add_argument('--replay', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    build(args.run, args.replay, args.output)
