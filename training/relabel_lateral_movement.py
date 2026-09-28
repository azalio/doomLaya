"""Relabel identical recorded inputs and reuse their verified semantic cache."""
import argparse
import collections
import copy
import hashlib
import json
from pathlib import Path
from training.lateral_movement import projected_label


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(source, cache_path, output, output_cache):
    if output.exists() or output_cache.exists():
        raise ValueError('Output exists')
    cache = json.loads(cache_path.read_text())
    manifest = dict(input_projection='movement-compact-v1', sources={},
        note='Same inputs, ordering and splits; offline lateral-first labels replace retreat-first labels. Retain a lateral direction while 2m are clear. Backward remains available when both sides are blocked and a threat is near. Evidence from two replayed MAP03 combat windows; this is not independent gameplay proof.',
        evidence=['runs/v031-map03-yellow-movement.json', 'runs/v031-map03-second-movement.json'],
        labeler_sha256=digest(Path('training/lateral_movement.py')),
        builder_sha256=digest(Path(__file__)), splits={})
    output.mkdir()
    for split in ('train', 'validation'):
        path = source / (split + '.json')
        if cache['identity']['data'][split] != digest(path):
            raise ValueError('Source cache identity differs')
        manifest['sources'][str(path)] = digest(path)
        rows = json.loads(path.read_text())
        changed = 0
        for row in rows:
            label = projected_label(row['state'])
            changed += row['label'] != label
            row['previous_label'] = row['label']
            row['label'] = label
            row['category'] = 'lateral_' + label
            row['source_type'] = 'offline_lateral_relabel'
        target = output / path.name
        target.write_text(json.dumps(rows, indent=2) + '\n')
        cache['identity']['data'][split] = digest(target)
        manifest['splits'][split] = dict(rows=len(rows), changed=changed, sha256=digest(target),
            categories=dict(collections.Counter(r['category'] for r in rows)))
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    cache['relabel_source'] = dict(path=str(cache_path), sha256=digest(cache_path),
        note='Only labels changed. Observations and frozen semantic answers are unchanged; trainer rechecks fresh predictions.')
    output_cache.write_text(json.dumps(cache, indent=2) + '\n')
    print(json.dumps(manifest, indent=2))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('data', 'cache', 'output', 'output-cache'):
        p.add_argument('--' + name, type=Path, required=True)
    a = p.parse_args()
    build(a.data, a.cache, a.output, a.output_cache)
