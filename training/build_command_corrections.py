"""Aggregate offline route corrections and successful behavior, preserving key facts."""
import argparse
import collections
import copy
import hashlib
import json
from pathlib import Path
import random

from doomlib.command_keys import FORMAT
from training.build_command_key_facts import project_keys
from training.build_regression_replay import resource_examples
from training.route_priority import labels


def build(replay, failures, successes, cases, answers, output):
    if output.exists():
        raise ValueError('Output exists')
    rng = random.Random(271227)
    pools = {split: [] for split in ('train', 'validation')}
    sources = {}

    def read(path, jsonl=False):
        sources[str(path)] = hashlib.sha256(path.read_bytes()).hexdigest()
        return [json.loads(line) for line in path.open()] if jsonl else json.loads(path.read_text())

    for split in pools:
        pools[split].extend(read(replay / (split + '.json')))
    for run in failures:
        for decision in read(run / 'decisions.jsonl', True):
            split = 'validation' if decision['tick'] // 700 % 5 == 0 else 'train'
            for row in resource_examples(decision['packet'], run.name, decision['tick'], decision['episode'], labels):
                if row['kind'] != 'command':
                    continue
                predicted = decision['answers']['command'].get('look_gate', {}).get('base_answer', decision['answers']['command'])['choice']
                prefix = 'new_error_' if predicted != row['label'] else 'new_agreement_'
                row['category'] = prefix + row['category'].removeprefix('correction_')
                pools[split].append(project_keys(row))
    for run in successes:
        summary = read(run / 'summary.json')
        if summary.get('levels_completed') != 1:
            raise ValueError('Successful replay must complete a level')
        completed_episode = summary['deaths']
        source_map = read(run / 'config.json')['args']['map'].lower()
        for decision in read(run / 'decisions.jsonl', True):
            if decision['episode'] != completed_episode:
                continue
            answer = decision['answers']['command']
            label = answer.get('look_gate', {}).get('base_answer', answer)['choice']
            split = 'validation' if decision['tick'] // 700 % 5 == 0 else 'train'
            pools[split].append(project_keys(dict(kind='command', label=label, category='completed_' + source_map + '_' + label,
                state=decision['packet']['state'], question=copy.deepcopy(decision['packet']['questions']['command']),
                source_run=run.name, source_tick=decision['tick'], source_episode=decision['episode'],
                source_type='behavior_replay_completed_episode', synthetic=False)))
    fixture = read(cases)['cases']
    results = read(answers)['results']
    if len(fixture) != len(results) or not all(result['passed'] for result in results):
        raise ValueError('Expected passing retention cases')
    for case, result in zip(fixture, results):
        if (case['source_run'], case['tick']) != (result['source_run'], result['tick']):
            raise ValueError('Retention order differs')
        answer = result['answers']['command']
        label = answer.get('look_gate', {}).get('base_answer', answer)['choice']
        pools['train'].append(project_keys(dict(kind='command', label=label, category='regression_retention',
            state=case['packet']['state'], question=copy.deepcopy(case['packet']['questions']['command']),
            source_run=case['source_run'], source_tick=case['tick'], source_type='development_probe_retention', synthetic=False)))
    output.mkdir()
    manifest = dict(input_projection=FORMAT, sources=sources, splits={},
        note='Offline route-label corrections on failed rollouts; normal-command behavioral replay from the final successful episode of completed runs; earlier replay and passing development probes retained. Every fifth 20-second source block is correlated development validation, not independent generalization. Live controller and action choices are unchanged.',
        builder_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        labeler_sha256=hashlib.sha256(Path('training/route_priority.py').read_bytes()).hexdigest(),
        projection_sha256=hashlib.sha256(Path('doomlib/command_keys.py').read_bytes()).hexdigest())
    seen = {}
    removed = collections.Counter()
    for split in pools:
        groups = collections.defaultdict(list)
        for row in pools[split]:
            groups[row['category']].append(row)
        rows = []
        for category, group in groups.items():
            rng.shuffle(group)
            cap = (320 if split == 'train' else 100) if category.startswith('new_error_') else (180 if split == 'train' else 70)
            rows.extend(group[:cap])
        rows.sort(key=lambda row: not row['category'].startswith(('new_error_', 'regression_retention')))
        clean = []
        for row in rows:
            key = json.dumps([row['state'], row['question']], sort_keys=True)
            if key in seen:
                removed[split + ('_conflict' if seen[key] != row['label'] else '_duplicate')] += 1
                continue
            seen[key] = row['label']
            clean.append(row)
        rng.shuffle(clean)
        path = output / (split + '.json')
        path.write_text(json.dumps(clean, indent=2))
        manifest['splits'][split] = dict(rows=len(clean), sha256=hashlib.sha256(path.read_bytes()).hexdigest(),
            categories=dict(collections.Counter(row['category'] for row in clean)))
    manifest['removed'] = dict(removed)
    (output / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps(manifest['splits'], indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('replay', 'cases', 'answers', 'output'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--failure', type=Path, action='append', required=True)
    parser.add_argument('--success', type=Path, action='append', default=[])
    args = parser.parse_args()
    build(args.replay, args.failure, args.success, args.cases, args.answers, args.output)
