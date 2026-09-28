"""Project recorded enemy types while preserving the verified frozen text inputs."""
import argparse
import collections
import copy
import hashlib
import json
from pathlib import Path
from doomlib.typed_movement import PROJECTION, semantic_state, typed_movement_input
from training.typed_movement import projected_label


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def build(source, cache_path, extra_runs, output, output_cache, fixture):
    if any(path.exists() for path in (output, output_cache, fixture)):
        raise ValueError('Output exists')
    rows = {split: json.loads((source / (split + '.json')).read_text()) for split in ('train', 'validation')}
    cache = json.loads(cache_path.read_text())
    needed = collections.defaultdict(dict)
    sources = {}
    for split, group in rows.items():
        if digest(source / (split + '.json')) != cache['identity']['data'][split]:
            raise ValueError('Source cache differs')
        for index, row in enumerate(group):
            needed[row['source_run']][row['source_tick']] = (split, index)
    changed = collections.Counter()
    for name, ticks in needed.items():
        path = Path('runs') / name / 'decisions.jsonl'
        sources[str(path)] = digest(path)
        for line in path.open():
            decision = json.loads(line)
            if decision['tick'] not in ticks:
                continue
            split, index = ticks.pop(decision['tick'])
            row = rows[split][index]
            packet = decision['packet']
            state, question = typed_movement_input(packet['state'], packet['questions']['movement'])
            if semantic_state(state) != row['state'] or question != row['question']:
                raise ValueError('Frozen semantic input changed')
            label = projected_label(state)
            changed[split] += row['label'] != label
            row.update(state=state, previous_label=row['label'], label=label,
                       category='typed_' + label, source_type='offline_typed_movement')
        if ticks:
            raise ValueError('Source observations are missing')
    seen = {json.dumps([r['state'], r['question']], sort_keys=True) for group in rows.values() for r in group}
    added = collections.Counter()
    cases = []
    for run in extra_runs:
        if not (run / 'summary.json').exists():
            raise ValueError('Only finalized recordings are accepted')
        path = run / 'decisions.jsonl'
        sources[str(path)] = digest(path)
        decisions = [json.loads(line) for line in path.open()]
        cutoff = decisions[-1]['tick'] * .8
        for index, decision in enumerate(decisions):
            answer = decision['answers'].get('movement')
            if not answer or decision['directive']['action'] != 'attack':
                continue
            head = decision['routing']['question_heads']['movement']
            if head['weights_sha256'] != cache['identity']['semantic_weights'] or head['input_projection'] != 'movement-compact-v1':
                raise ValueError('Frozen movement branch differs')
            packet = decision['packet']
            state, question = typed_movement_input(packet['state'], packet['questions']['movement'])
            label = projected_label(state)
            if label == 'backward' and answer['choice'] != label and len(cases) < 16:
                cases.append(dict(source_run=run.name, tick=decision['tick'], check='expected_movement',
                                  expected_movement=label, recorded_movement=answer['choice'], packet=packet))
            if index % 6 and label == answer['choice']:
                continue
            key = json.dumps([state, question], sort_keys=True)
            if key in seen:
                continue
            seen.add(key)
            split = 'train' if decision['tick'] < cutoff else 'validation'
            rows[split].append(dict(kind='movement', state=state, question=copy.deepcopy(question), label=label,
                previous_label=answer['choice'], category='typed_' + label, source_run=run.name,
                source_tick=decision['tick'], source_episode=decision['episode'],
                source_type='offline_typed_movement', synthetic=False))
            semantic = answer.get('numeric_residual', {}).get('semantic_answer', answer)
            cache['answers'][split].append(dict(probabilities=semantic['probabilities']))
            added[split] += 1
    output.mkdir()
    manifest = dict(input_projection=PROJECTION, sources=sources, changed=dict(changed), added=dict(added), splits={},
        builder_sha256=digest(__file__), labeler_sha256=digest('training/typed_movement.py'),
        projection_sha256=digest('doomlib/typed_movement.py'), source_manifest_sha256=digest(source / 'manifest.json'),
        note='Recorded development observations only. Original splits retained; extra recordings use temporal 80/20. Same-map development, no held-out claim. The text branch receives exactly the original v1 state; only the learned residual sees observed Demon/Spectre geometry.')
    for split, group in rows.items():
        path = output / (split + '.json')
        path.write_text(json.dumps(group, indent=2) + '\n')
        cache['identity']['data'][split] = digest(path)
        manifest['splits'][split] = dict(rows=len(group), sha256=digest(path),
            categories=dict(collections.Counter(r['category'] for r in group)))
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    cache['typed_projection'] = dict(source_cache_sha256=digest(cache_path),
        semantic_inputs_unchanged=True, source_manifest_sha256=digest(output / 'manifest.json'))
    output_cache.write_text(json.dumps(cache, indent=2) + '\n')
    fixture.write_text(json.dumps(dict(note=manifest['note'], source_sha256=sources, cases=cases), indent=2) + '\n')
    print(json.dumps(dict(changed=dict(changed), added=dict(added), splits=manifest['splits'], cases=len(cases)), indent=2))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('data', 'cache', 'output', 'output-cache', 'fixture'):
        p.add_argument('--' + name, type=Path, required=True)
    p.add_argument('--run', type=Path, action='append', default=[])
    a = p.parse_args()
    build(a.data, a.cache, a.run, a.output, a.output_cache, a.fixture)
