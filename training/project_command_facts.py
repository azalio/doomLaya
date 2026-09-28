"""Apply the same compact command observations used by the inference server."""
import argparse
import collections
import hashlib
import json
from pathlib import Path

from doomlib.command_facts import FORMAT, STABLE_FORMAT, BINNED_FORMAT, command_facts_input, stable_command_facts_input, binned_command_facts_input
from training.build_regression_replay import project


def project_row(source, lift_context_only=False, bands=False):
    row = project(source)
    projector = binned_command_facts_input if bands else stable_command_facts_input if lift_context_only else command_facts_input
    row['state'], row['question'] = projector(row['raw_state'], row['question'])
    return row


def build(data, output, lift_context_only=False, bands=False):
    if output.exists():
        raise ValueError('Output exists')
    seen = {}
    results = {}
    removed = collections.Counter()
    conflicts = []
    manifest = dict(input_projection=BINNED_FORMAT if bands else STABLE_FORMAT if lift_context_only else FORMAT, lift_context_only=lift_context_only or bands, bands=bands, source_manifest=json.loads((data / 'manifest.json').read_text()),
        note='Exact production command fact projection. Generic current action retained only in v1; v2 retains selected board/ride lift execution context; nearest reachable sightings by item name, owned/ammo facts, visible/recent enemy distances, mechanism counts and lift phases. Optional measurement bands preserve the offered actions; no action recommendations or option masking.',
        sources={}, splits={}, projection_sha256=hashlib.sha256(Path('doomlib/command_facts.py').read_bytes()).hexdigest(),
        builder_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    for split in ('train', 'validation'):
        path = data / (split + '.json')
        manifest['sources'][str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
        clean = []
        for index, source in enumerate(json.loads(path.read_text())):
            row = project_row(source, lift_context_only, bands)
            key = json.dumps([row['state'], row['question']], sort_keys=True)
            if key in seen:
                prior = seen[key]
                if prior['label'] != row['label']:
                    conflicts.append(dict(split=split, index=index, label=row['label'], source_run=row['source_run'], source_tick=row['source_tick'], original=prior))
                else:
                    removed[split + '_duplicate'] += 1
                continue
            seen[key] = dict(split=split, index=index, label=row['label'], source_run=row['source_run'], source_tick=row['source_tick'])
            clean.append(row)
        results[split] = clean
    if conflicts:
        raise ValueError('Conflicting projected observations: ' + json.dumps(conflicts[:10]))
    output.mkdir()
    for split, rows in results.items():
        path = output / (split + '.json')
        path.write_text(json.dumps(rows, indent=2))
        manifest['splits'][split] = dict(rows=len(rows), sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            categories=dict(collections.Counter(row['category'] for row in rows)))
    manifest['removed'] = dict(removed)
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps(dict(splits=manifest['splits'], removed=manifest['removed']), indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--lift-context-only', action='store_true')
    parser.add_argument('--bands', action='store_true')
    args = parser.parse_args()
    build(args.data, args.output, args.lift_context_only, args.bands)
