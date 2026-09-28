"""Record offline target-order labels and the unchanged semantic ranker scores."""
import argparse
import collections
import copy
import hashlib
import json
from pathlib import Path
from doomlib.enemy_ranking import FORMAT, STOP, ranking_input
from training.build_map3_enemy_sequences import order_for


def digest(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def build(base, train_runs, validation_runs, output, cache_path, cases_path):
    if any(path.exists() for path in (output, cache_path, cases_path)):
        raise ValueError('Output exists')
    if set(train_runs) & set(validation_runs):
        raise ValueError('Run overlaps splits')
    primary = digest(base / 'model.safetensors')
    rows, answers = {s: [] for s in ('train', 'validation')}, {s: [] for s in ('train', 'validation')}
    seen, sources, cases = set(), {}, []
    for split, runs in [('train', train_runs), ('validation', validation_runs)]:
        for run in runs:
            if not (run / 'summary.json').exists():
                raise ValueError('Unfinished source run')
            path = run / 'decisions.jsonl'; sources[str(path)] = digest(path)
            for d in map(json.loads, path.open()):
                if d['directive']['action'] != 'attack' or 'enemy' not in d['answers']:
                    continue
                head = d['routing']['question_heads']['enemy']
                if head['weights_sha256'] != primary or head['input_projection'] != FORMAT:
                    raise ValueError('Semantic enemy head differs')
                packet = d['packet']; order = order_for(packet)
                state, question, orders = ranking_input(packet['state'], packet['questions']['enemy'])
                identity = json.dumps([state, question], sort_keys=True)
                if identity in seen:
                    continue
                seen.add(identity)
                answer = d['answers']['enemy']['ranking_head']
                semantic = answer.get('numeric_residual', {}).get('semantic_answer', answer)
                if set(semantic['probabilities']) != set(question['criteria']):
                    raise ValueError('Semantic options differ')
                row = dict(kind='enemy', state=state, question=question, label=order[0],
                    target_ranking=order+[STOP], sequence_label=next(k for k,v in orders.items() if v==order),
                    enemy_sequences=orders, category='observed_target_order', source_run=run.name,
                    source_tick=d['tick'], source_episode=d['episode'], synthetic=False,
                    source_type='offline_target_order_correction')
                rows[split].append(row); answers[split].append(dict(probabilities=semantic['probabilities']))
                actual = packet['enemy_sequences'][d['answers']['enemy']['choice']][0]
                if actual != order[0]:
                    cases.append(dict(source_run=run.name, tick=d['tick'],
                        packet=dict(state=packet['state'], questions={'enemy':copy.deepcopy(packet['questions']['enemy'])},
                                    enemy_sequences=packet['enemy_sequences']),
                        check='expected_enemy_first', expected_enemy=order[0]))
    if not all(rows.values()):
        raise ValueError('Empty split')
    output.mkdir()
    manifest = dict(builder_sha256=digest(__file__), labeler_sha256=digest('training/build_map3_enemy_sequences.py'),
        sources=sources, splits={}, note='Observed target-order labels use only available enemies and the accepted target. Distinct source runs and projected inputs per split; same-map development, no held-out map or seed claim. No runtime teacher.')
    for split, group in rows.items():
        path = output/(split+'.json'); path.write_text(json.dumps(group,indent=2)+'\n')
        manifest['splits'][split] = dict(rows=len(group), sha256=digest(path))
    (output/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    cache_path.write_text(json.dumps(dict(identity=dict(semantic_weights=primary, data={s:manifest['splits'][s]['sha256'] for s in rows}),
                                         answers=answers, sources=sources),indent=2)+'\n')
    cases_path.write_text(json.dumps(dict(note='Observed development errors included in supervised data; not independent gameplay validation.',
                                         sources=sources,cases=cases),indent=2)+'\n')
    print(json.dumps(dict(splits=manifest['splits'],regressions=len(cases))))


if __name__ == '__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('base','output','cache','cases'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--train-runs',type=Path,nargs='+',required=True)
    p.add_argument('--validation-runs',type=Path,nargs='+',required=True)
    a=p.parse_args();build(a.base,a.train_runs,a.validation_runs,a.output,a.cache,a.cases)
