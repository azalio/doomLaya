"""Freeze full MAP02 demonstrations with combat-priority counterfactuals."""
import argparse
import collections
import copy
import hashlib
import json
import math
import random
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from doomlib.policy import request
from doomlib.mission import Mission,map_data
from doomlib.combat import WEAPON_NAMES
import vizdoom


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--train',type=Path,nargs='+',required=True)
    parser.add_argument('--validation',type=Path,nargs='+',required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if {p.resolve() for p in args.train}&{p.resolve() for p in args.validation}:raise ValueError('Source runs overlap')
    args.output.mkdir(parents=True,exist_ok=False)
    mission=Mission(map_data(Path(vizdoom.__file__).parent/'freedoom2.wad','MAP02'))
    manifest={'label_source':'offline demonstrations and explicit combat counterfactuals','sources':{}}
    for split,paths in [('train',args.train),('validation',args.validation)]:
        rng=random.Random(661 if split=='train' else 662);groups=collections.defaultdict(list);snapshots=[]
        for path in paths:
            source=path/'examples.json'
            manifest['sources'][path.name]={'split':split,'sha256':hashlib.sha256(source.read_bytes()).hexdigest(),'summary':json.loads((path/'summary.json').read_text())}
            for row in json.loads(source.read_text()):
                if row['kind']=='command' and 'Previous command result: No navigable path' in row['state']:continue
                groups[(row['kind'],row['category'])].append(row)
            with (path/'telemetry.jsonl').open() as handle:
                for line in handle:
                    s=json.loads(line)
                    if s['tick']%70==0:snapshots.append(s)
        records=[]
        for (kind,category),rows in groups.items():
            cap=(150 if category=='attack' else 80) if kind=='command' else 50
            if split=='validation':cap=20
            rng.shuffle(rows);records.extend(rows[:cap])
        for i in range(240 if split=='train' else 60):
            s=copy.deepcopy(rng.choice(snapshots));stage=i%6
            s.update(hp=rng.choice([50,75,100]),armor=rng.choice([0,50]),door=None,execution={},target_failures={},command_failures={})
            for slot,entry in s['inventory'].items():entry.update(owned=int(slot in ('1','2','3')),ammo=0 if slot=='1' else rng.randint(8,30))
            s['inventory']['2']['ammo']=rng.randint(20,100)
            s['inventory']['3']['owned']=int(stage!=2)
            distance=rng.uniform(1.6,4.5) if stage==0 else rng.uniform(7,18)
            enemy=dict(id=30000+i,name=rng.choice(['Demon','DoomImp','ShotgunGuy','Zombieman']),x=s['x']+distance*32,y=s['y'],distance=round(distance,1),bearing=0,aim_bearing=0,visible=True)
            s['enemies']=[enemy]
            memory={m['id']:dict(m,distance=math.dist((s['x'],s['y']),(m['x'],m['y']))/32,bearing=0) for m in mission.data['key_markers'] if m['color'] not in s.get('keys',())}
            for item in s['items']:
                if item['category']=='Key':continue
                memory[item['id']]=dict(item)
            command=('backpedal_' if stage==0 else 'shoot_')+str(enemy['id'])
            if stage in (2,3,4):
                name,category={2:('Shotgun','Weapon'),3:('Shell','Ammo'),4:('Medikit','Health')}[stage]
                item=dict(id=40000+i,name=name,category=category,x=s['x']+32,y=s['y'],distance=1.,bearing=0.)
                memory[item['id']]=item;command='collect_'+str(item['id'])
                if stage==3:
                    s['inventory']['2']['ammo']=0;s['inventory']['3']['ammo']=0
                if stage==4:s['hp']=rng.randint(5,25)
            if stage==5:
                # Empty guns must not displace a loaded pistol with melee.
                s['inventory']['3']['ammo']=0
            packet=request(s,memory,mission)
            slots=[slot for slot in (3,2,1) if s['inventory'][str(slot)]['owned'] and (slot==1 or s['inventory'][str(slot)]['ammo']>0)]
            gold={'command':command,'weapon':WEAPON_NAMES[slots[0]]}
            for kind,q in packet['questions'].items():
                records.append(dict(state=packet['state'],question=q,label=gold[kind],kind=kind,
                                    category=packet['commands'][command]['action'] if kind=='command' else gold[kind],
                                    source_type='combat_counterfactual',synthetic=True,source_run='counterfactual-'+split,source_tick=i,stage=stage))
        prior=json.loads(Path('training/v3',split+'.json').read_text());rng.shuffle(prior)
        records.extend(prior[:(60 if split=='train' else 20)])
        rng.shuffle(records)
        for row in records:assert row['label'] in row['question']['criteria']
        target=args.output/(split+'.json');target.write_text(json.dumps(records,indent=2))
        manifest[split]={'rows':len(records),'sha256':hashlib.sha256(target.read_bytes()).hexdigest(),'groups':dict(collections.Counter(r['kind']+':'+r['category'] for r in records))}
        print(split,manifest[split],flush=True)
    (args.output/'manifest.json').write_text(json.dumps(manifest,indent=2))


if __name__=='__main__':main()
