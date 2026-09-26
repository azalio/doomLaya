"""Freeze grouped MAP02 demonstrations and explicit counterfactual states."""
import argparse
import collections
import copy
import hashlib
import json
import random
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from policy import request
from mission import Mission,map_data
from combat import WEAPON_NAMES
import vizdoom


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--train',nargs='+',type=Path,required=True)
    parser.add_argument('--validation',nargs='+',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    a=parser.parse_args()
    if set(a.train)&set(a.validation):raise ValueError('Source runs overlap')
    a.output.mkdir(parents=True,exist_ok=False)
    mission=Mission(map_data(Path(vizdoom.__file__).parent/'freedoom2.wad','MAP02'))
    manifest={'map':'MAP02','label_source':'offline teacher and explicitly marked counterfactuals','sources':{}}
    for split,paths in [('train',a.train),('validation',a.validation)]:
        rng=random.Random(441 if split=='train' else 442)
        records=[];groups=collections.defaultdict(list)
        for path in paths:
            rows=json.loads((path/'examples.json').read_text())
            manifest['sources'][path.name]={'split':split,'sha256':hashlib.sha256((path/'examples.json').read_bytes()).hexdigest()}
            for row in rows:
                # Failed combat traces teach combat only, not their failed route.
                if row.get('source_type')=='offline_teacher' and row['kind']=='command' and row['category'] not in ('attack','pickup','open_door'):continue
                if row['kind']=='command' and 'Previous command result: No navigable path' in row['state']:continue
                groups[(row['kind'],row['category'])].append(row)
        for group,rows in groups.items():
            rng.shuffle(rows);records.extend(rows[:(130 if split=='train' else 30)])
        base=json.loads((paths[0]/'telemetry.jsonl').read_text().splitlines()[0])
        for i in range(100 if split=='train' else 25):
            s=copy.deepcopy(base);s.update(hp=rng.choice([45,70,100]),armor=rng.choice([0,50,100]),enemies=[],items=[],keys=[],door=None,command_failures={},target_failures={},execution={})
            s['inventory']['3']={'owned':1,'ammo':rng.choice([0,8,20])}
            s['inventory']['2']['ammo']=rng.choice([0,20,60])
            s['switches']=[dict(v,activated=True,locked=False,distance=10.,phase='call') for v in mission.data['switches']]
            memory={};stage=i%5
            if stage==0:
                s['x'],s['y']=-256,704
                key={'id':10000+i,'name':'YellowCard','category':'Key','x':-256,'y':800,'distance':3.,'bearing':0.}
                memory[key['id']]=key;label='collect_'+str(key['id'])
            elif stage==1:
                s['keys']=['yellow'];label='exit'
            elif stage==2:
                s['command_failures']={'exit':'No traversable route with the current keys'};label='explore'
            elif stage==3:
                s['keys']=['yellow'];s['door']={'id':37,'x':480,'y':-736,'distance':1.5,'bearing':0,'required_key':'yellow','locked':False};label='open_door'
            else:
                lift=next(v for v in s['switches'] if v.get('kind')=='lift');lift.update(activated=False,phase=rng.choice(['call','board','ride']))
                label='switch_'+str(lift['id'])
            packet=request(s,memory,mission)
            usable=[slot for slot in (3,2,1) if s['inventory'][str(slot)]['owned'] and (slot==1 or s['inventory'][str(slot)]['ammo']>0)]
            labels={'command':label,'weapon':WEAPON_NAMES[usable[0]]}
            for kind,q in packet['questions'].items():
                records.append({'state':packet['state'],'question':q,'label':labels[kind],'kind':kind,'category':packet['commands'][label]['action'] if kind=='command' else labels[kind],
                                'source_run':'counterfactual-'+split,'source_tick':i,'source_type':'counterfactual','synthetic':True,'stage':stage})
        prior=json.loads(Path('training/v3',split+'.json').read_text());rng.shuffle(prior)
        records.extend(prior[:(240 if split=='train' else 60)])
        rng.shuffle(records)
        for row in records:assert row['label'] in row['question']['criteria']
        dest=a.output/(split+'.json');dest.write_text(json.dumps(records,indent=2))
        manifest[split]={'rows':len(records),'sha256':hashlib.sha256(dest.read_bytes()).hexdigest(),'groups':dict(collections.Counter(r['kind']+':'+r['category'] for r in records))}
        print(split,manifest[split],flush=True)
    (a.output/'manifest.json').write_text(json.dumps(manifest,indent=2))


if __name__=='__main__':main()
