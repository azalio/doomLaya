"""Mix delayed weapon-aware demonstrations, replay, and controlled inventory examples."""
import argparse,collections,copy,hashlib,json,random,re,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from combat import WEAPON_NAMES,AMMO_COST
from policy import request


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def synthetic_weapon(base,rng,index):
    shells=rng.choice([0,1,2,3,5,10,20,40]);bullets=rng.choice([0,1,10,50,150])
    ordinary,double=rng.choice([(True,False),(False,True),(True,True),(False,False)])
    inventory={str(i):dict(owned=int(i in (1,2) or (i==3 and ordinary) or (i==8 and double)),ammo=shells if i in (3,8) else bullets if i in (2,4) else 0) for i in range(1,10)}
    band=re.search(r'Enemy range: (\w+)',base['state']).group(1)
    distance={'none':None,'melee':1.,'close':3.,'medium':10.,'far':30.}[band]
    enemy=dict(id=1,name='DoomImp',distance=distance,x=0,y=0)
    observation=dict(hp=100,armor=0,inventory=inventory,enemies=[] if distance is None else [enemy],door=None)
    packet=request(observation,{},None)
    state=re.sub(r'Inventory: [^\n]*',next(x for x in packet['state'].splitlines() if x.startswith('Inventory:')),base['state'])
    label=next(WEAPON_NAMES[i] for i in (8,3,2,1) if inventory[str(i)]['owned'] and inventory[str(i)]['ammo']>=AMMO_COST[i])
    return dict(base,state=state,question=packet['questions']['weapon'],label=label,kind='weapon',category=label,
                synthetic=True,source_type='controlled_weapon_inventory',source_variant=index)


def main():
    p=argparse.ArgumentParser();p.add_argument('--demonstrations',type=Path,required=True);p.add_argument('--replay',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    a.output.mkdir(exist_ok=False);manifest=dict(source_type='offline training only',source_sha256={});training_keys=set()
    for split,extra,retain in [('train',448,640),('validation',112,160)]:
        rng=random.Random(9281 if split=='train' else 9282)
        sources=[root/(split+'.json') for root in (a.demonstrations,a.replay)]
        for path in sources:manifest['source_sha256'][str(path)]=digest(path)
        rows=json.loads(sources[0].read_text());replay=json.loads(sources[1].read_text());rng.shuffle(replay)
        weapon_rows=[r for r in rows if r['kind']=='weapon']
        rows.extend(synthetic_weapon(rng.choice(weapon_rows),rng,i) for i in range(extra))
        rows.extend(replay[:retain]);rng.shuffle(rows)
        unique=[];seen=set()
        for row in rows:
            key=json.dumps({k:row[k] for k in ('state','question','label')},sort_keys=True)
            if key in seen or (split=='validation' and key in training_keys):continue
            seen.add(key);unique.append(row)
        if split=='train':training_keys=seen
        path=a.output/(split+'.json');path.write_text(json.dumps(unique,indent=2))
        manifest[split]=dict(rows=len(unique),sha256=digest(path),kinds=dict(collections.Counter(r['kind'] for r in unique)),weapon_labels=dict(collections.Counter(r['label'] for r in unique if r['kind']=='weapon')))
        print(split,manifest[split],flush=True)
    (a.output/'manifest.json').write_text(json.dumps(manifest,indent=2))

if __name__=='__main__':main()
