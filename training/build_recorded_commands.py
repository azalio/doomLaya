"""Apply offline command labels to exact recorded model inputs."""
import argparse
import collections
import copy
import hashlib
import json
import random
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from training.correct_reachable_rollout import corrections


def recorded_row(row,decision):
    if row['kind']!='command':raise ValueError('Only command labels are supported')
    result=copy.deepcopy(row)
    result['state']=decision['packet']['state']
    result['question']=copy.deepcopy(decision['packet']['questions']['command'])
    if result['label'] not in result['question']['criteria']:
        raise ValueError('Offline label is not an offered command')
    result['source_type']='offline_teacher_label_on_exact_recorded_command'
    result['model_choice']=decision['answers']['command']['choice']
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--runs',nargs='+',type=Path,required=True)
    p.add_argument('--replay',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if a.output.exists():p.error('output exists')
    manifest=dict(note='Offline teacher labels on unchanged recorded states and questions. Model rollout episodes split by parity. All disagreements and every fourth agreement retained. Late-route diagnostic cases from heads54 episode0 are now development training data, not held-out evaluation.',sources={},runs={},splits={})
    pools={'train':[],'validation':[]}
    for run in a.runs:
        decisions={d['tick']:d for d in map(json.loads,(run/'decisions.jsonl').read_text().splitlines())}
        rows,counts=corrections(run,1,True)
        commands=[r for r in rows if r['kind']=='command'];same=sum(r['state']==decisions[r['source_tick']]['packet']['state'] for r in commands)
        manifest['runs'][run.name]=dict(commands=len(commands),regenerated_state_exact=same,action_pairs=dict(counts))
        for name in ('config.json','telemetry.jsonl','decisions.jsonl'):
            path=run/name;manifest['sources'][str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
        for i,row in enumerate(commands):
            value=recorded_row(row,decisions[row['source_tick']])
            if value['label']==value['model_choice'] and i%4:continue
            pools['train' if row['source_episode']%2==0 else 'validation'].append(value)
    seen={};splits={}
    for split in ('train','validation'):
        rng=random.Random(8291 if split=='train' else 8292)
        path=a.replay/(split+'.json');manifest['sources'][str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
        groups=collections.defaultdict(list)
        for row in json.loads(path.read_text()):
            if row['kind']=='command':groups[row['label']].append(row)
        for values in groups.values():
            rng.shuffle(values);pools[split].extend(values[:150 if split=='train' else 40])
        rows=[]
        for row in pools[split]:
            key=json.dumps([row['state'],row['question']],sort_keys=True)
            if key in seen:
                if seen[key]!=row['label']:raise ValueError('Conflicting command labels')
                continue
            seen[key]=row['label'];rows.append(row)
        rng.shuffle(rows);splits[split]=rows
        manifest['splits'][split]=dict(rows=len(rows),labels=dict(collections.Counter(r['label'] for r in rows)),sources=dict(collections.Counter(r['source_type'] for r in rows)))
    a.output.mkdir()
    for split,rows in splits.items():
        path=a.output/(split+'.json');path.write_text(json.dumps(rows,indent=2))
        manifest['splits'][split]['sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
    (a.output/'manifest.json').write_text(json.dumps(manifest,indent=2));print(json.dumps(manifest,indent=2))


if __name__=='__main__':main()
