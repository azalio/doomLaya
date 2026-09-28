"""Append offline item corrections using frozen semantic scores recorded by Laya."""
import argparse
import copy
import hashlib
import json
from pathlib import Path
from doomlib.compact_item import CATEGORY_FORMAT, category_item_input
from training.route_resupply_balanced import labels


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('data', 'cache', 'output', 'output-cache'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--run', type=Path, action='append', required=True)
    args = parser.parse_args()
    if args.output.exists() or args.output_cache.exists():
        raise ValueError('Output exists')
    rows = {s: json.loads((args.data / (s + '.json')).read_text()) for s in ('train', 'validation')}
    cache = json.loads(args.cache.read_text())
    for split in rows:
        if cache['identity']['data'][split] != digest(args.data / (split + '.json')):
            raise ValueError('Cache data differs')
    seen = {json.dumps([r['state'], r['question']], sort_keys=True) for group in rows.values() for r in group}
    added = {s: 0 for s in rows}
    sources = {}
    for run in args.run:
        decisions = [json.loads(line) for line in (run / 'decisions.jsonl').open()]
        sources[str(run / 'decisions.jsonl')] = digest(run / 'decisions.jsonl')
        for index, decision in enumerate(decisions):
            if index % 4 or 'item' not in decision['answers']:
                continue
            packet = decision['packet']
            expected = next(((value, category) for kind, value, category in labels(packet) if kind == 'item'), None)
            if expected is None:
                continue
            label, category = expected
            answer = decision['answers']['item']
            if label == answer['choice'] and index % 24:
                continue
            head = decision['routing']['question_heads']['item']
            if head['weights_sha256'] != cache['identity']['semantic_weights'] or head['input_projection'] != CATEGORY_FORMAT:
                raise ValueError('Frozen item head differs')
            semantic = answer['numeric_residual']['semantic_answer']['probabilities']
            state, question = category_item_input(packet['state'], copy.deepcopy(packet['questions']['item']))
            if set(semantic) != set(question['criteria']):
                raise ValueError('Semantic options differ')
            key = json.dumps([state, question], sort_keys=True)
            if key in seen:
                continue
            seen.add(key)
            split = 'validation' if decision['tick'] // 140 % 5 == 0 else 'train'
            rows[split].append(dict(kind='item', label=label, category=category, state=state, question=question,
                raw_state=packet['state'], source_run=run.name, source_tick=decision['tick'], source_episode=decision['episode'],
                source_type='offline_balanced_resupply_trace', synthetic=False))
            cache['probabilities'][split].append([semantic[k] for k in question['criteria']])
            added[split] += 1
    args.output.mkdir()
    manifest = dict(input_projection=CATEGORY_FORMAT, builder_sha256=digest(Path(__file__)),
        labeler_source_sha256={name: digest(Path(name)) for name in ('training/route_resupply_balanced.py', 'training/route_resupply.py', 'training/build_map3_resources.py')},
        source_manifest=json.loads((args.data / 'manifest.json').read_text()), sources=sources, added=added, splits={},
        note='Same-map development observations. Four-second blocks, every fifth block for validation. Frozen semantic scores copied from recorded responses; no runtime teacher and no held-out-map claim.')
    for split, group in rows.items():
        path = args.output / (split + '.json')
        path.write_text(json.dumps(group, indent=2) + '\n')
        manifest['splits'][split] = dict(rows=len(group), sha256=digest(path))
    (args.output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    cache['identity']['data'] = {s: manifest['splits'][s]['sha256'] for s in rows}
    cache['trace_provenance'] = dict(original_cache_sha256=digest(args.cache), sources=sources, added=added,
        primary_weights_and_projection_verified=True)
    args.output_cache.write_text(json.dumps(cache, indent=2) + '\n')
    print(json.dumps(dict(added=added, splits=manifest['splits']), indent=2))


if __name__ == '__main__':
    main()
