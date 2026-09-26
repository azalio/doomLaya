"""Offline curriculum for choosing reachable supplies from explicit observations."""
import argparse,collections,hashlib,json,random,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from policy import request
from training.build_committed_dataset import examples
from training.map2_teacher import labels


def synthetic(rng,index):
    shells=rng.choice([0,1,2,4,10,25,40]);bullets=rng.choice([0,5,30,80])
    owned={1,2}|rng.choice([{3},{8},{3,8},set()])
    inventory={str(i):dict(owned=int(i in owned),ammo=shells if i in (3,8) else bullets if i in (2,4) else 0) for i in range(1,10)}
    state=dict(hp=rng.choice([15,25,40,60,80,100]),armor=rng.choice([0,30,70,100]),inventory=inventory,
               enemies=[],walls={'left':10.,'right':10.},door=None,keys=[],x=0,y=0)
    names=[('Shotgun','Weapon'),('SuperShotgun','Weapon'),('RedCard','Key'),('BlueCard','Key'),('YellowCard','Key'),
           ('Medikit','Health'),('Stimpack','Health'),('GreenArmor','Armor'),('ShellBox','Ammo'),('ClipBox','Ammo')]
    rng.shuffle(names);memory={};reachable=set()
    for i,(name,category) in enumerate(names):
        distance=round(rng.uniform(1,40),1);oid=index*20+i
        access=rng.random()<(0.2 if category=='Key' else 0.8)
        item=dict(id=oid,name=name,category=category,distance=distance,x=distance*32,y=i,reachable=access)
        memory[oid]=item
        if access:reachable.add((item['x'],item['y']))
    state['reachable_items']={str(k):v['reachable'] for k,v in memory.items()}
    prior=rng.choice(list(memory.values()))
    state['execution']=dict(action='pickup',target_id=prior['id'],status='executing',movement=None)
    class Geometry:
        @staticmethod
        def nearest(point):return point
    packet=request(state,memory,None);gold=labels(packet,state,reachable,Geometry())
    if not gold['command'].startswith('collect_'):return []
    result=list(examples(packet,gold,'synthetic_reachable_supplies',index,0,True))
    for row in result:row.update(synthetic=True,source_type='controlled_reachable_supplies')
    return result


def main():
    p=argparse.ArgumentParser();p.add_argument('--demonstrations',type=Path,required=True);p.add_argument('--replay',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    a.output.mkdir(exist_ok=False);manifest={'source_type':'offline curriculum only','source_sha256':{}};training=set()
    for split,count,retain in [('train',300,500),('validation',80,125)]:
        rng=random.Random(9621 if split=='train' else 9622);paths=[root/(split+'.json') for root in (a.demonstrations,a.replay)]
        for path in paths:manifest['source_sha256'][str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
        rows=json.loads(paths[0].read_text());replay=[r for r in json.loads(paths[1].read_text()) if r['kind'] in ('weapon','enemy','movement')];rng.shuffle(replay);rows+=replay[:retain]
        for i in range(count):rows+=synthetic(rng,i+(0 if split=='train' else 10000))
        rng.shuffle(rows);unique=[];seen=set()
        for row in rows:
            key=json.dumps({k:row[k] for k in ('state','question')},sort_keys=True)
            if key in seen or (split=='validation' and key in training):continue
            seen.add(key);unique.append(row)
        if split=='train':training=seen
        path=a.output/(split+'.json');path.write_text(json.dumps(unique,indent=2))
        manifest[split]=dict(rows=len(unique),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),kinds=dict(collections.Counter(r['kind'] for r in unique)))
        print(split,manifest[split],flush=True)
    (a.output/'manifest.json').write_text(json.dumps(manifest,indent=2))

if __name__=='__main__':main()
