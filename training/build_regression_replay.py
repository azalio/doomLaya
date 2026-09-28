"""Offline cross-map resource corrections and replay; never used by the player."""
import argparse
import collections
import copy
import hashlib
import json
import random
from pathlib import Path
from doomlib.compact_item import category_item_input, CATEGORY_FORMAT
from doomlib.policy import request
from doomlib.decision_questions import factorize, with_commitment
from training.build_map3_resources import labels


def resource_examples(packet, run, tick, episode, labeler=labels):
    for kind,label,category in labeler(packet):
        if kind not in packet['questions']:
            continue
        yield dict(kind=kind,label=label,category='correction_'+category,
                   state=packet['state'],question=copy.deepcopy(packet['questions'][kind]),
                   source_run=run,source_tick=tick,source_episode=episode,
                   source_type='offline_resource_correction',synthetic=False)


def project(source):
    row=copy.deepcopy(source)
    row['raw_state']=row.get('raw_state',row['state'])
    row['raw_question']=copy.deepcopy(row.get('raw_question',row['question']))
    if row['kind']=='item':
        row['state'],row['question']=category_item_input(row['raw_state'],row['raw_question'])
    elif row['kind']=='command':
        row['state']='\n'.join(line for line in row['raw_state'].splitlines() if not line.startswith('Current command:'))
        q=row['question'];q.pop('look_observation',None);q['criteria'].pop('look_back',None)
        if 'Finish the level alive.' in q['instructions']:
            q['instructions']=q['instructions'][q['instructions'].index('Finish the level alive.'):]
    else:raise ValueError('Only command and item heads are supported')
    if row['label'] not in row['question']['criteria']:raise ValueError('Unavailable label')
    return row


def synthetic_resources(split,count=512,labeler=labels):
    rng=random.Random(270931 if split=='train' else 270932)
    for index in range(count):
        hp=rng.choice((10,30,60,82,100)) if split=='train' else rng.choice((12,32,62,84,100))
        armor=rng.choice((0,30,80,150));owned=rng.choice((False,True));shells=rng.choice((0,5,15,35))
        inventory={str(k):dict(owned=int(k in (1,2) or (k==3 and owned)),ammo=0) for k in range(1,10)}
        for k in (2,4):inventory[str(k)]['ammo']=rng.choice((20,60,100))
        for k in (3,8):inventory[str(k)]['ammo']=shells
        specs=[(rng.choice(('Medikit','Stimpack')),'Health',rng.uniform(.3,5)),
               ('Shotgun','Weapon',rng.uniform(6,22)),('GreenArmor','Armor',rng.uniform(6,25)),
               ('ShellBox','Ammo',rng.uniform(2,18)),('Clip','Ammo',rng.uniform(2,18))]
        if index%3==0:specs.append(('YellowCard','Key',rng.uniform(12,55)))
        specs += [(rng.choice(('ArmorBonus','HealthBonus')),'',rng.uniform(2,25)) for _ in range(rng.choice((0,3,7)))]
        items={}
        for name,category,distance in specs:
            key=str(rng.randrange(100,9999))
            while key in items:key=str(rng.randrange(100,9999))
            items[key]=dict(id=key,name=name,category=category or ('Health' if name=='HealthBonus' else 'Armor'),distance=round(distance,1),x=distance*32,y=0,z=0,reachable=True)
        observation=dict(hp=hp,armor=armor,inventory=inventory,enemies=[],door=None,keys=[],execution={},reachable_items=list(items.values()))
        packet=with_commitment(factorize(request(observation,items,None)))
        for row in resource_examples(packet,'synthetic_regression_'+split,index,0,labeler):
            row.update(category='synthetic_'+row['category'].removeprefix('correction_'),synthetic=True,source_type='synthetic_resource_contrast')
            yield row


def build(kind,replays,train_runs,validation_runs,output,route_priority=False):
    from training.route_priority import labels as route_labels
    labeler=route_labels if route_priority else labels
    if output.exists():raise ValueError('Output exists')
    if set(map(Path.resolve,train_runs))&set(map(Path.resolve,validation_runs)):raise ValueError('A source run occurs in both splits')
    sources={};pools={};rng=random.Random(270933);removed=collections.Counter();seen={};results={}
    for split,runs in (('train',train_runs),('validation',validation_runs)):
        rows=[]
        for run in runs:
            p=run/'decisions.jsonl';sources[str(p)]=hashlib.sha256(p.read_bytes()).hexdigest();groups=collections.defaultdict(list)
            for line in p.open():
                d=json.loads(line)
                for row in resource_examples(d['packet'],run.name,d['tick'],d['episode'],labeler):
                    if row['kind']==kind:groups[row['category']].append(row)
            for group in groups.values():
                rng.shuffle(group);rows.extend(group[:180 if split=='train' else 90])
        rows.extend(r for r in synthetic_resources(split,512 if split=='train' else 128,labeler) if r['kind']==kind)
        for replay in replays:
            p=replay/(split+'.json');sources[str(p)]=hashlib.sha256(p.read_bytes()).hexdigest()
            groups=collections.defaultdict(list)
            for row in json.loads(p.read_text()):
                if row['kind']==kind:
                    row=copy.deepcopy(row);row['category']='replay_'+replay.name+'_'+row.get('category','unspecified');groups[row['category']].append(row)
            for group in groups.values():
                rng.shuffle(group)
                cap=80 if route_priority else (600 if kind=='command' and replay.name.startswith('map2-') else len(group))
                rows.extend(group[:cap if split=='train' else min(cap,300)])
        pools[split]=rows
    for split in ('train','validation'):
        clean=[]
        for source in pools[split]:
            row=project(source);key=json.dumps([row['state'],row['question']],sort_keys=True)
            if key in seen:
                removed[split+('_conflict' if seen[key][1]!=row['label'] else '_duplicate')]+=1
                continue
            seen[key]=(split,row['label']);clean.append(row)
        rng.shuffle(clean);results[split]=clean
    output.mkdir();manifest=dict(kind=kind,offline_labeler='route-priority-v1' if route_priority else 'map3-resources-v1',input_projection=CATEGORY_FORMAT if kind=='item' else 'without-current-command-v1',
        note='Offline resource labels on failed MAP01/MAP02 runs, with distinct successful runs reserved for development validation. Existing MAP02/MAP03 replay keeps its split allocation. Original checkpoints have seen some replay and maps: this is retention/development fitting, not independent generalization. Synthetic examples include full health with a nearby medikit and useful distant alternatives, vary inventory/armor, and do not always offer keys. Corrections precede replay; global duplicate/conflict removal is train-first and counted. Runtime choices and controller are unchanged. With --route-priority, corrected mission-priority labels replace the resource labeler and replay is capped at 80 per category. Labeler identity is recorded separately.',
        sources=sources,train_runs=list(map(str,train_runs)),validation_runs=list(map(str,validation_runs)),removed=dict(removed),splits={},builder_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),labeler_sha256=hashlib.sha256(Path('training/route_priority.py' if route_priority else 'training/build_map3_resources.py').read_bytes()).hexdigest())
    for split,rows in results.items():
        p=output/(split+'.json');p.write_text(json.dumps(rows,indent=2))
        manifest['splits'][split]=dict(rows=len(rows),sha256=hashlib.sha256(p.read_bytes()).hexdigest(),categories=dict(collections.Counter(r['category'] for r in rows)))
    (output/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps(dict(splits=manifest['splits'],removed=dict(removed)),indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--kind',choices=['command','item'],required=True);p.add_argument('--replay',type=Path,action='append',required=True);p.add_argument('--train-run',type=Path,action='append',default=[]);p.add_argument('--validation-run',type=Path,action='append',default=[]);p.add_argument('--output',type=Path,required=True);p.add_argument('--route-priority',action='store_true');a=p.parse_args();build(a.kind,a.replay,a.train_run,a.validation_run,a.output,a.route_priority)
