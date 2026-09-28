"""Prepare recorded movement geometry, offline labels and frozen semantic scores."""
import argparse
import collections
import hashlib
import json
from pathlib import Path
from doomlib.compact_movement import FORMAT, compact_movement_input, movement_facts
from training.build_map3_retreat import choose_movement


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(train_runs, validation_runs, base, output, cache_path):
    if output.exists() or cache_path.exists():
        raise ValueError('Output exists')
    if set(train_runs) & set(validation_runs):
        raise ValueError('Source run overlaps splits')
    rows = {'train': [], 'validation': []}
    answers = {s: [] for s in rows}
    sources, seen, counts = {}, {}, collections.Counter()
    semantic_weights = None
    for split, runs in [('train', train_runs), ('validation', validation_runs)]:
        for run in runs:
            if not (run / 'summary.json').exists():
                raise ValueError('Only finalized runs are accepted')
            path = run / 'decisions.jsonl'
            sources[str(path)] = digest(path)
            for line in path.open():
                decision = json.loads(line)
                answer = decision['answers'].get('movement')
                if not answer or decision['directive']['action'] != 'attack':
                    continue
                head = decision['routing']['question_heads']['movement']
                semantic_weights = semantic_weights or head['weights_sha256']
                if head['weights_sha256'] != semantic_weights or head.get('input_projection') != FORMAT:
                    raise ValueError('Semantic movement weights or projection changed')
                packet = decision['packet']
                question = packet['questions']['movement']
                facts = movement_facts(packet['state'], question)
                label = choose_movement([dict(distance=facts['nearest'], visible=True)], facts['clearance'], facts['current'])
                state, projected_question = compact_movement_input(packet['state'], question)
                identity = json.dumps([state, projected_question], sort_keys=True)
                if identity in seen:
                    if seen[identity] != label:
                        raise ValueError('Contradicting observed labels')
                    counts['duplicates_' + split] += 1
                    continue
                seen[identity] = label
                semantic = answer.get('numeric_residual', {}).get('semantic_answer', answer)
                if set(semantic['probabilities']) != set(question['criteria']):
                    raise ValueError('Semantic options differ')
                rows[split].append(dict(kind='movement', state=state, question=projected_question, label=label,
                    category='observed_' + label, source_run=run.name, source_tick=decision['tick'],
                    source_episode=decision['episode'], source_type='offline_retreat_geometry', synthetic=False))
                answers[split].append(dict(probabilities=semantic['probabilities']))
    if not all(rows.values()):
        raise ValueError('Empty movement split')
    output.mkdir()
    manifest = dict(builder_sha256=digest(Path(__file__)), labeler_sha256=digest(Path('training/build_map3_retreat.py')),
        projection_sha256=digest(Path('doomlib/compact_movement.py')), sources=sources, input_projection=FORMAT,
        counts=dict(counts), splits={}, note='Offline retreat labels use exactly the rounded observed geometry available to the model. Validation source runs differ from training, with projected duplicates removed train-first. Same-map development only; no held-out-map claim. Frozen semantic answers come from recorded model responses.')
    for split, group in rows.items():
        path = output / (split + '.json')
        path.write_text(json.dumps(group, indent=2) + '\n')
        manifest['splits'][split] = dict(rows=len(group), sha256=digest(path),
            categories=dict(collections.Counter(r['category'] for r in group)))
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    cache = dict(identity=dict(semantic_weights=semantic_weights, config=digest(base / 'rl_agent_config.json'),
                 data={s: manifest['splits'][s]['sha256'] for s in rows}), answers=answers,
                 source_manifest_sha256=digest(output / 'manifest.json'), requires_fresh_api_audit=True)
    cache_path.write_text(json.dumps(cache, indent=2) + '\n')
    print(json.dumps(dict(counts=dict(counts), splits=manifest['splits']), indent=2))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--train-runs', nargs='+', type=Path, required=True)
    p.add_argument('--validation-runs', nargs='+', type=Path, required=True)
    for name in ('base', 'output', 'cache'):
        p.add_argument('--' + name, type=Path, required=True)
    a = p.parse_args()
    build(a.train_runs, a.validation_runs, a.base, a.output, a.cache)
