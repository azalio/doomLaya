"""Counterfactual rear-clearance pairs inside full recorded movement contexts."""
import argparse
import collections
import copy
import hashlib
import json
import random
import re
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from movement_questions import describe_movement


def augment(row):
    if not re.search(r'Enemy range: (close|melee);',row['state']):return []
    walls=re.search(r'Clearance: left ([0-9.]+)m, right ([0-9.]+)m',row['state'])
    if not walls:return []
    body={'left':max(0,float(walls[1])-.5),'right':max(0,float(walls[2])-.5)}
    side=max(body,key=body.get)
    if body[side]<1.5:return []
    match=re.search(r'Movement: ([^.]+)',row['state']);current=match[1] if match else None
    rows=[]
    for name,back,direction in [('back_open',8.,'backward'),('back_blocked',.25,'strafe_'+side)]:
        result=copy.deepcopy(row);clearance=dict(body,back=back)
        result['question']=describe_movement(row['question'],clearance,current)
        result['label']='continue' if current==direction else direction
        assert result['label'] in result['question']['criteria']
        result.update(synthetic=True,source_type='counterfactual_rear_clearance_in_recorded_context',pair_variant=name,clearance=clearance)
        rows.append(result)
    return rows


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--replay',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.exists():p.error('output exists')
    seen=set();splits={};manifest=dict(note='Recorded movement contexts with synthetic rear clearance. Original state, enemy range, resources and previous movement are unchanged. Original rows retained. The held-out death window is excluded.',sources={},splits={})
    for split in ('train','validation'):
        path=a.replay/(split+'.json');original=[r for r in json.loads(path.read_text()) if r['kind']=='movement'];manifest['sources'][str(path)]=hashlib.sha256(path.read_bytes()).hexdigest();pool=list(original)
        for row in original:pool.extend(augment(row))
        rows=[]
        for row in pool:
            key=json.dumps([row['state'],row['question']],sort_keys=True)
            if key in seen:continue
            seen.add(key);rows.append(row)
        random.Random(29091 if split=='train' else 29092).shuffle(rows);splits[split]=rows
        manifest['splits'][split]=dict(rows=len(rows),new_pairs=sum(r.get('source_type')=='counterfactual_rear_clearance_in_recorded_context' for r in rows)//2,labels=dict(collections.Counter(r['label'] for r in rows)))
    a.output.mkdir()
    for split,rows in splits.items():
        path=a.output/(split+'.json');path.write_text(json.dumps(rows,indent=2));manifest['splits'][split]['sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
    (a.output/'manifest.json').write_text(json.dumps(manifest,indent=2));print(json.dumps(manifest,indent=2))


if __name__=='__main__':main()
