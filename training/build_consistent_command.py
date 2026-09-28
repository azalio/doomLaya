"""Apply one offline command rubric to all recorded states, including successes."""
import argparse
import collections
import hashlib
import json
from pathlib import Path
import random

from doomlib.command_keys import FORMAT
from training.build_command_key_facts import project_keys
from training.build_regression_replay import resource_examples, project
from doomlib.compact_item import CATEGORY_FORMAT
from training.route_priority import labels


def build(runs, cases, output, kind="command"):
    if kind not in ("command", "item"):
        raise ValueError("Unsupported question kind")
    project_row = project_keys if kind == "command" else project
    if output.exists():
        raise ValueError('Output exists')
    rng = random.Random(271701)
    pools = {split: collections.defaultdict(list) for split in ('train', 'validation')}
    sources = {}
    provenance = {}
    def digest(path):
        with path.open('rb') as stream:
            sources[str(path)] = hashlib.file_digest(stream, 'sha256').hexdigest()
    for run in runs:
        config = run / 'config.json'
        digest(config)
        run_config = json.loads(config.read_text())
        source_map = run_config['args']['map']
        diagnostic_policy = run_config.get('diagnostic_policy') or run_config.get('laya_health', {}).get('diagnostic_policy')
        summary_path = run / 'summary.json'
        digest(summary_path)
        summary = json.loads(summary_path.read_text())
        source = run / 'decisions.jsonl'
        digest(source)
        with source.open() as stream:
            for line in stream:
                decision = json.loads(line)
                # Stop-after-level records also contain decisions on the next map.
                # Only source episodes up to the first level transition are retained.
                if summary.get('levels_completed') and decision['episode'] > summary['deaths']:
                    continue
                provenance[(run.name, decision['tick'])] = decision['episode']
                split = 'validation' if decision['tick'] // 700 % 5 == 0 else 'train'
                for row in resource_examples(decision['packet'], run.name, decision['tick'], decision['episode'], labels):
                    if row['kind'] != kind:
                        continue
                    row['category'] = row['category'].removeprefix('correction_')
                    row['source_map'] = source_map
                    row['source_type'] = 'consistent_offline_route_rubric'
                    if diagnostic_policy:
                        row['source_diagnostic_policy'] = diagnostic_policy
                    pools[split][(source_map, row['category'])].append(project_row(row))
    digest(cases)
    regressions = []
    for case in json.loads(cases.read_text())['cases']:
        rows = [row for row in resource_examples(case['packet'], case['source_run'], case['tick'], provenance.get((case['source_run'], case['tick'])), labels) if row['kind'] == kind]
        if not rows and kind == 'item':
            continue
        if len(rows) != 1:
            raise ValueError('Missing regression label')
        row = project_row(rows[0])
        row['category'] = 'regression_retention'
        row['source_type'] = 'development_probe_consistent_rubric'
        regressions.append(row)
    output.mkdir()
    seen = {}
    removed = collections.Counter()
    manifest = dict(kind=kind, input_projection=FORMAT if kind == "command" else CATEGORY_FORMAT, sources=sources, splits={},
        note='One offline route rubric labels every state from successes and failures. No behavioral-cloning labels from old decisions. Per-map and per-category sampling; every fifth 20-second temporal block is correlated development validation. Regression cases are explicit training retention. This is not independent generalization or live teacher control.',
        builder_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        labeler_sha256=hashlib.sha256(Path('training/route_priority.py').read_bytes()).hexdigest(),
        projection_sha256=hashlib.sha256(Path('doomlib/command_keys.py' if kind == 'command' else 'doomlib/compact_item.py').read_bytes()).hexdigest())
    for split, groups in pools.items():
        rows = list(regressions) if split == 'train' else []
        for group in groups.values():
            rng.shuffle(group)
            rows.extend(group[:160 if split == 'train' else 60])
        clean = []
        for row in rows:
            key = json.dumps([row['state'], row['question']], sort_keys=True)
            if key in seen:
                if seen[key] != row['label']:
                    raise ValueError('Conflicting same-observation labels')
                removed[split + '_duplicate'] += 1
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
    parser.add_argument('--run', type=Path, action='append', required=True)
    parser.add_argument('--cases', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--kind', choices=['command', 'item'], default='command')
    args = parser.parse_args()
    build(args.run, args.cases, args.output, args.kind)
