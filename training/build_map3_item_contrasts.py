"""Offline resource contrasts with factual item categories; no live item policy."""
import argparse,collections,copy,hashlib,json,random
from pathlib import Path
from doomlib.compact_item import CATEGORY_FORMAT,category_item_input
from doomlib.policy import request
from doomlib.decision_questions import factorize,with_commitment
from training.build_map3_resources import candidates


def synthetic(split):
    rng=random.Random(19471 if split=='train' else 19472)
    for index in range(768 if split=='train' else 192):
        offset=0 if split=='train' else 1
        hp=rng.choice((3,25,55,80,100)) if split=='train' else rng.choice((4,28,58,82,99))
        armor=rng.choice((0,30,80));shells=rng.choice((0,6,25));bullets=rng.choice((0,40,90))
        inventory={str(k):dict(owned=int(k in (1,2,3)),ammo=0) for k in range(1,10)}
        for k in (2,4):inventory[str(k)]['ammo']=bullets
        for k in (3,8):inventory[str(k)]['ammo']=shells
        specs=[(rng.choice(('Stimpack','Medikit')),'Health',rng.choice((2,8,18,30,42,54))+offset),
               ('BlueCard','Key',rng.choice((4,12,24,36,48,60))+offset),
               ('GreenArmor','Armor',rng.choice((4,16,28,40,52))+offset),
               ('ShellBox','Ammo',rng.choice((3,9,15,25))+offset),
               ('Chaingun','Weapon',rng.choice((6,18,30,42))+offset)]
        specs+=[(rng.choice(('ArmorBonus','HealthBonus')),'',rng.uniform(2,60)) for _ in range(rng.choice((3,7,11)))]
        items={}
        for name,category,distance in specs:
            category=category or ('Armor' if name=='ArmorBonus' else 'Health');key=str(rng.randrange(100,9999))
            while key in items:key=str(rng.randrange(100,9999))
            items[key]=dict(id=key,name=name,category=category,distance=round(distance,1),x=distance*32,y=0,z=0,reachable=True)
        state=dict(hp=hp,armor=armor,inventory=inventory,enemies=[],door=None,keys=[],execution={},reachable_items=list(items.values()))
        packet=with_commitment(factorize(request(state,items,None)));scored,_=candidates(packet)
        if not scored:raise ValueError('Missing synthetic target')
        label=scored[0][1];category=packet['targets']['item'][label]['category'].lower()
        yield dict(kind='item',label=label,category='synthetic_'+category,state=packet['state'],question=packet['questions']['item'],source_run='synthetic_resource_contrasts_'+split,source_tick=index,source_type='synthetic_offline_resource_contrast',synthetic=True)


def build(data,output):
    if output.exists():raise ValueError('Output exists')
    sources={};seen={};result={};removed=collections.Counter()
    for split in ('train','validation'):
        p=data/(split+'.json');sources[str(p)]=hashlib.sha256(p.read_bytes()).hexdigest();result[split]=[]
        for original in json.loads(p.read_text())+list(synthetic(split)):
            row=copy.deepcopy(original);row['raw_state']=row.get('raw_state',row['state']);row['raw_question']=copy.deepcopy(row.get('raw_question',row['question']))
            row['state'],row['question']=category_item_input(row['raw_state'],row['raw_question'])
            key=json.dumps([row['state'],row['question']],sort_keys=True)
            if key in seen:
                if seen[key]!=row['label']:raise ValueError('Conflicting effective inputs')
                removed[split]+=1;continue
            seen[key]=row['label'];result[split].append(row)
    output.mkdir();manifest=dict(input_projection=CATEGORY_FORMAT,note='Uses observed category from the original Items line and compact distance-first criteria. Original IDs, names, distances, reachability and ownership are preserved; all choices remain available. Original split allocations retained. Synthetic examples vary health, armor, ammunition and distances, with disjoint synthetic health values and non-bonus distance grids per item category in validation; bonus distances are sampled independently. Labels use the existing offline resource scorer. MAP03 held-out run remains validation-only. Development validation; no success or independent-map claim.',sources=sources,removed=dict(removed),splits={},builder_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),projection_sha256=hashlib.sha256(Path('doomlib/compact_item.py').read_bytes()).hexdigest())
    for split,rows in result.items():
        p=output/(split+'.json');p.write_text(json.dumps(rows,indent=2));manifest['splits'][split]=dict(rows=len(rows),sha256=hashlib.sha256(p.read_bytes()).hexdigest(),categories=dict(collections.Counter(r['category'] for r in rows)))
    (output/'manifest.json').write_text(json.dumps(manifest,indent=2));print(json.dumps(manifest,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--data',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();build(a.data,a.output)
