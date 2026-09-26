"""Train movement decisions from explicit geometry; never used by the executor."""
import argparse
import collections
import hashlib
import json
import random
import sys
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from policy import request
from decision_questions import factorize,with_commitment,without_action_continuation
from movement_questions import with_movement_clearance


def pairs(rng,index):
    safe=rng.choice(['left','right']);other='right' if safe=='left' else 'left'
    body={safe:round(rng.uniform(3,12),2),other:round(rng.uniform(.0,.75),2)}
    inventory={str(i):dict(owned=int(i in (1,2,3,8)),ammo=100 if i==2 else 12 if i in (3,8) else 0) for i in range(1,10)}
    current=rng.choice(['backward','strafe_left','strafe_right',None]);oid=rng.randint(1,900000)
    hp=rng.choice([12,38,57,80,100]);keys=rng.choice([[],['red'],['blue'],['red','blue']]);angle=rng.choice(['DoomImp','Spectre','Demon','ShotgunGuy'])
    ordering=rng.getrandbits(32);rows=[];near=round(rng.uniform(.8,4.5),1);far=round(rng.uniform(7,18),1);back_open=round(rng.uniform(4,12),2);back_tight=round(rng.uniform(0,.75),2)
    for variant,distance,back in [('close_back_open',near,back_open),('close_back_blocked',near,back_tight),('medium_side_open',far,back_open)]:
        clearance=dict(body,back=back)
        enemy=dict(id=oid,name=angle,distance=distance,x=distance*32,y=0,z=0,bearing=0,visible=True)
        s=dict(hp=hp,armor=50,inventory=inventory,walls={k:round(v+.5,2) for k,v in body.items()},door=None,keys=keys,enemies=[enemy],switches=[],x=0,y=0,z=0,execution=dict(action='attack',target_id=oid,status='executing',movement=current),reachable_items={})
        packet=without_action_continuation(with_commitment(factorize(request(s,{},SimpleNamespace(exit=None)))))
        packet=with_movement_clearance(packet,clearance)
        movement='backward' if variant=='close_back_open' else 'strafe_'+safe
        label='continue' if movement==current else movement
        question=packet['questions']['movement'];options=list(question['criteria'].items());random.Random(ordering).shuffle(options);question['criteria']=dict(options)
        assert label in question['criteria']
        rows.append(dict(state=packet['state'],question=question,label=label,kind='movement',category='attack',source_run='paired_body_clearance',source_tick=index,source_episode=0,synthetic=True,source_type='paired_geometry_supervision',pair_variant=variant,pair_group=index,clearance=clearance))
    return rows


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--replay',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.exists():p.error('output exists')
    seen=set();splits={};manifest=dict(note='Synthetic geometry pairs and unchanged original movement replay. Recorded death-window cases are excluded. No runtime movement policy.',sources={},splits={})
    for split,count in [('train',120),('validation',36)]:
        rng=random.Random(53219 if split=='train' else 53220);rows=[]
        for i in range(count):rows.extend(pairs(rng,i+(0 if split=='train' else 10000)))
        path=a.replay/(split+'.json');replay=json.loads(path.read_text());manifest['sources'][str(path)]=hashlib.sha256(path.read_bytes()).hexdigest();rows.extend(r for r in replay if r['kind']=='movement')
        unique=[]
        for row in rows:
            key=json.dumps([row['state'],row['question']],sort_keys=True)
            if key in seen:continue
            seen.add(key);unique.append(row)
        rng.shuffle(unique);splits[split]=unique;manifest['splits'][split]=dict(rows=len(unique),labels=dict(collections.Counter(r['label'] for r in unique)),synthetic=sum(r['synthetic'] for r in unique))
    a.output.mkdir()
    for split,rows in splits.items():
        path=a.output/(split+'.json');path.write_text(json.dumps(rows,indent=2));manifest['splits'][split]['sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
    (a.output/'manifest.json').write_text(json.dumps(manifest,indent=2));print(json.dumps(manifest,indent=2))


if __name__=='__main__':main()
