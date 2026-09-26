"""Offline paired supervision for reachable keys, empty shells, and healing."""
import argparse
import collections
import copy
import hashlib
import json
import random
import sys
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from doomlib.policy import request
from doomlib.decision_questions import factorize,with_commitment,without_action_continuation,mask_unreachable_items


def paired_examples(rng,index):
    ids=rng.sample(range(1,900000),12)
    distances=[round(rng.uniform(1.5,5.5),1),round(rng.uniform(1.5,5.5),1),round(rng.uniform(10,38),1)]
    inventory={str(i):dict(owned=int(i in (1,2,3,8)),ammo=150 if i==2 else 0) for i in range(1,10)}
    switches=[dict(id=ids[j+4],name='Lift',kind='lift',distance=round(rng.uniform(8,60),1),x=0,y=0,phase='call',activated=False,locked=False,route_keys=[color]) for j,color in enumerate(('red','blue'))]
    memory={}
    for j,(name,category) in enumerate([('ShellBox','Ammo'),('Medikit','Health'),('YellowCard','Key')]):
        memory[ids[j]]=dict(id=ids[j],name=name,category=category,distance=distances[j],x=distances[j]*32,y=j*32,reachable=True)
    for j,(name,category) in enumerate([('Clip','Ammo'),('HealthBonus','Health'),('ArmorBonus','Armor')],start=6):
        distance=round(rng.uniform(1,30),1)
        memory[ids[j]]=dict(id=ids[j],name=name,category=category,distance=distance,x=distance*32,y=j*32,reachable=True)
    previous=rng.choice([None,ids[0],ids[1],ids[2],ids[4],ids[5]])
    action='wait' if previous is None else 'use_switch' if previous in ids[4:6] else 'pickup'
    execution=dict(action=action,target_id=previous,status='waiting' if previous is None else 'executing',movement=None)
    rows=[];ordering_seed=rng.getrandbits(32);loaded_shells=rng.choice([24,40,50]);walls={'left':round(rng.uniform(.3,12),1),'right':round(rng.uniform(.3,12),1)}
    # The world and previous goal are shared within each contrastive group.
    for variant in ('loaded','empty_shells','critical_health','blocked_key','all_keys'):
        inv=copy.deepcopy(inventory);shells=0 if variant=='empty_shells' else loaded_shells
        for slot in ('3','8'):inv[slot]['ammo']=shells
        items=copy.deepcopy(memory);mechanisms=copy.deepcopy(switches);keys=['red','blue']
        hp=rng.choice([9,18,28]) if variant=='critical_health' else 100
        if variant=='blocked_key':
            items[ids[2]]['reachable']=False
            mechanisms.append(dict(id=ids[9],name='Door switch',kind='door',distance=round(rng.uniform(5,30),1),x=0,y=0,phase='call',activated=False,locked=False,key='red'))
        if variant=='all_keys':keys.append('yellow');items.pop(ids[2])
        state=dict(hp=hp,armor=100,inventory=inv,walls=walls,door=None,keys=keys,enemies=[],switches=mechanisms,x=0,y=0,z=0,execution=execution,reachable_items={str(k):v['reachable'] for k,v in items.items()})
        packet=mask_unreachable_items(without_action_continuation(with_commitment(factorize(request(state,items,SimpleNamespace(exit={'line':1}))))))
        target={'loaded':ids[2],'empty_shells':ids[0],'critical_health':ids[1]}.get(variant)
        command='pickup' if target is not None else 'use_switch' if variant=='blocked_key' else 'exit'
        for kind,label in [('command',command)]+([('item',str(target))] if target is not None else []):
            question=copy.deepcopy(packet['questions'][kind]);options=list(question['criteria'].items());random.Random(ordering_seed+(kind=='item')).shuffle(options);question['criteria']=dict(options)
            assert label in question['criteria']
            rows.append(dict(state=packet['state'],question=question,label=label,kind=kind,category=command,source_run='paired_late_route',source_tick=index,source_episode=0,synthetic=True,source_type='paired_late_route_resource_supervision',pair_variant=variant,pair_group=index))
    return rows


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--replay',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.exists():p.error('output exists')
    seen=set();splits={};manifest=dict(note='Synthetic offline labels plus replay. No live teacher. Development validation selects weights; recorded late-game cases are not included.',sources={},splits={})
    for split,count in [('train',120),('validation',35)]:
        rng=random.Random(87111 if split=='train' else 87112);rows=[]
        for i in range(count):rows.extend(paired_examples(rng,i+(0 if split=='train' else 10000)))
        path=a.replay/(split+'.json');original=json.loads(path.read_text());manifest['sources'][str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
        for kind,cap in [('command',480),('item',600)]:
            pool=[r for r in original if r['kind']==kind];rng.shuffle(pool)
            rows.extend(pool[:cap if split=='train' else cap//4])
        unique=[]
        for row in rows:
            key=json.dumps([row['state'],row['question']],sort_keys=True)
            if key in seen:continue
            seen.add(key);unique.append(row)
        rng.shuffle(unique);splits[split]=unique
        manifest['splits'][split]=dict(rows=len(unique),kinds=dict(collections.Counter(r['kind'] for r in unique)),variants=dict(collections.Counter(r.get('pair_variant','replay') for r in unique)))
    a.output.mkdir()
    for split,rows in splits.items():
        path=a.output/(split+'.json');path.write_text(json.dumps(rows,indent=2));manifest['splits'][split]['sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
    (a.output/'manifest.json').write_text(json.dumps(manifest,indent=2));print(json.dumps(manifest,indent=2))


if __name__=='__main__':main()
