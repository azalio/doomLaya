"""Weapon-only projection plus synthetic ammunition/ownership contrasts, offline."""
import argparse,collections,copy,hashlib,itertools,json,random
from pathlib import Path
from doomlib.compact_weapon import FORMAT,compact_weapon_input
from doomlib.policy import request
from doomlib.decision_questions import factorize,with_commitment
from training.build_map3_combat import gold


def synthetic(split):
    values=(0,1,5,20) if split=='train' else (0,2,14,30)
    rockets=(0,1) if split=='train' else (0,2)
    rng=random.Random(1642 if split=='train' else 1643)
    for index,(owned,bullets,shells,rocket_ammo) in enumerate(itertools.product(itertools.product((False,True),repeat=3),values,values,rockets)):
        inventory={str(k):dict(owned=int(k in (1,2) or (k in (3,4,5) and owned[k-3])),ammo=bullets if k in (2,4) else shells if k in (3,8) else rocket_ammo if k==5 else 0) for k in range(1,10)}
        enemy_distance=rng.choice((1.,5.,20.)) if split=='train' else rng.choice((1.2,4.,12.))
        state=dict(hp=rng.choice((30,60,100)) if split=='train' else rng.choice((7,45,85)),armor=0,inventory=inventory,door=None,keys=[],walls=dict(left=3,right=3),enemies=[dict(id=1,name='DoomImp',distance=enemy_distance,bearing=0,visible=True,x=0,y=0,z=0)],execution={})
        packet=with_commitment(factorize(request(state,{},None)))
        label=next(label for kind,label,category in gold(packet,rapid_fire=True) if kind=='weapon')
        yield dict(kind='weapon',state=packet['state'],question=packet['questions']['weapon'],label=label,category='ammo_contrast_'+label,source_run='synthetic_weapon_inventory_'+split,source_tick=index,source_type='synthetic_observed_inventory_contrast',synthetic=True)


def build(source,output,heldout_run=None):
    if output.exists():raise ValueError('Output exists')
    if heldout_run and not (heldout_run/'summary.json').exists():raise ValueError('Held-out live run must be finished')
    sources={};out={};seen={};removed=collections.Counter()
    for split in ('train','validation'):
        p=source/(split+'.json');sources[str(p)]=hashlib.sha256(p.read_bytes()).hexdigest();rows=[r for r in json.loads(p.read_text()) if r['kind']=='weapon'];rows+=list(synthetic(split))
        if heldout_run and split=='validation':
            p=heldout_run/'decisions.jsonl';sources[str(p)]=hashlib.sha256(p.read_bytes()).hexdigest()
            for decision in map(json.loads,p.open()):
                if decision['episode']!=0:continue
                packet=decision['packet'];label=next(label for kind,label,category in gold(packet,rapid_fire=True) if kind=='weapon')
                rows.append(dict(kind='weapon',state=packet['state'],question=packet['questions']['weapon'],label=label,category='live_first_life_'+label,source_run=heldout_run.name,source_tick=decision['tick'],source_episode=0,source_type='offline_relabel_heldout_run',synthetic=False))
        out[split]=[]
        for original in rows:
            row=copy.deepcopy(original);row['raw_state']=row['state'];row['state'],row['question']=compact_weapon_input(row['state'],row['question'])
            key=json.dumps([row['state'],row['question']])
            if key in seen:
                if seen[key]!=row['label']:raise ValueError('Conflicting projected weapon labels')
                removed[split]+=1;continue
            seen[key]=row['label'];out[split].append(row)
    output.mkdir();manifest=dict(input_projection=FORMAT,note='Same existing offline weapon priorities and labels; all original weapon choices retained. State contains only observed health, inventory and enemies. Synthetic ownership/ammunition contrasts use separate nonzero ammo values and HP values for validation; zero ammunition is shared as a concept. Optional first life of a complete later run is validation only. Same-map development, not gameplay proof.',sources=sources,splits={},removed=dict(removed),builder_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),projection_sha256=hashlib.sha256(Path('doomlib/compact_weapon.py').read_bytes()).hexdigest())
    for split,rows in out.items():
        p=output/(split+'.json');p.write_text(json.dumps(rows,indent=2));manifest['splits'][split]=dict(rows=len(rows),sha256=hashlib.sha256(p.read_bytes()).hexdigest(),categories=dict(collections.Counter(r['category'] for r in rows)))
    (output/'manifest.json').write_text(json.dumps(manifest,indent=2));print(json.dumps(manifest,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--data',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--heldout-run',type=Path);a=p.parse_args();build(a.data,a.output,a.heldout_run)
