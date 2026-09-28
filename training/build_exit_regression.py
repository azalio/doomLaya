"""Offline exit-state corrections with route replay and completed-mechanism contrasts."""
import argparse
import collections
import copy
import hashlib
import json
import random
from pathlib import Path
from training.build_regression_replay import resource_examples,project
from training.route_priority import labels


def completed_mechanisms(row):
    if row['label']!='use_switch' or row['category']!='correction_route_continue_route' or 'exit' not in row['question']['criteria']:
        return None
    result=copy.deepcopy(row)
    # A factual counterfactual for training only: no available mechanism remains.
    for field in ('state','raw_state'):
        if field in result:
            result[field]='\n'.join(line for line in result[field].splitlines() if not line.startswith('Available mechanisms:'))
    for field in ('question','raw_question'):
        if field in result:result[field]['criteria'].pop('use_switch',None)
    result.update(label='exit',category='completed_mechanisms_exit',synthetic=True,
                  source_type='counterfactual_completed_mechanisms',counterfactual='Remove available mechanisms and their action; retain health, inventory, enemies, keys and items.')
    return result


def build(replay,failure,output):
    if output.exists():raise ValueError('Output exists')
    rng=random.Random(271003);sources={};result={};seen={};dropped=collections.Counter()
    for split in ('train','validation'):
        rows=[];path=replay/(split+'.json');sources[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
        original=json.loads(path.read_text());groups=collections.defaultdict(list)
        for row in original:groups[row['category']].append(row)
        for group in groups.values():
            rng.shuffle(group);rows.extend(group[:40 if split=='train' else 20])
        contrasts=[c for r in original if (c:=completed_mechanisms(r)) is not None]
        rng.shuffle(contrasts);rows.extend(contrasts[:300 if split=='train' else 150])
        if split=='train':
            path=failure/'decisions.jsonl';sources[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest();groups=collections.defaultdict(list)
            for d in map(json.loads,path.open()):
                for row in resource_examples(d['packet'],failure.name,d['tick'],d['episode'],labels):
                    if row['kind']=='command':
                        row=project(row);row['category']='failure_'+row['category'];groups[row['category']].append(row)
            for group in groups.values():rng.shuffle(group);rows.extend(group[:120])
        clean=[]
        for row in rows:
            key=json.dumps([row['state'],row['question']],sort_keys=True)
            if key in seen:
                dropped[split+('_conflict' if seen[key]!=row['label'] else '_duplicate')]+=1;continue
            seen[key]=row['label'];clean.append(row)
        rng.shuffle(clean);result[split]=clean
    output.mkdir();manifest=dict(note='Corrective finetune after the second MAP01 failure. All new live-failure states are training-only. Prior replay preserves its original development split. Synthetic completed-mechanism contrasts inherit their parent split. No independent-map or gameplay claim; offline only.',input_projection='without-current-command-v1',sources=sources,splits={},removed=dict(dropped),builder_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),labeler_sha256=hashlib.sha256(Path('training/route_priority.py').read_bytes()).hexdigest())
    for split,rows in result.items():
        path=output/(split+'.json');path.write_text(json.dumps(rows,indent=2));manifest['splits'][split]=dict(rows=len(rows),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),categories=dict(collections.Counter(r['category'] for r in rows)))
    (output/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n');print(json.dumps(manifest['splits'],indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--replay',type=Path,required=True);p.add_argument('--failure',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();build(a.replay,a.failure,a.output)
