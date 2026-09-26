"""Offline contrastive examples for completed lift routes and distant combat."""
import argparse,collections,copy,hashlib,json,random,sys
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from doomlib.policy import request
from training.build_committed_dataset import examples


def sample(rng,index):
    colors=['red','blue'];keys=rng.choice([[],['red'],['blue'],['red','blue'],['red','blue','yellow']])
    inventory={str(i):dict(owned=int(i in (1,2,3,8)),ammo=50 if i in (3,8) else 200 if i in (2,4) else 0) for i in range(1,10)}
    switches=[]
    for j,color in enumerate(colors):
        distance=round(rng.uniform(5,60),1);oid=index*10+j+100
        switches.append(dict(id=oid,name='Lift',kind='lift',distance=distance,x=distance*32,y=j*32,phase='call',activated=False,locked=False,route_keys=[color]))
    for j,color in enumerate(keys):
        if color=='yellow' or rng.random()<.35:continue
        distance=round(rng.uniform(5,60),1);oid=index*10+j+103
        switches.append(dict(id=oid,name='Door switch',kind='door',distance=distance,x=distance*32,y=(j+3)*32,phase='call',activated=False,locked=False,key=color))
    rng.shuffle(switches)
    advancing=[s for s in switches if s['kind']=='door' or any(c not in keys for c in s['route_keys'])]
    if not advancing and 'yellow' not in keys:return []
    enemy_distance=rng.choice([None,round(rng.uniform(3,18),1),round(rng.uniform(23,65),1)])
    enemies=[] if enemy_distance is None else [dict(id=index*10+109,name='DoomImp',distance=enemy_distance,x=enemy_distance*32,y=0,z=0,bearing=0,visible=True)]
    state=dict(hp=rng.choice([15,29,50,85,100,120]),armor=100,inventory=inventory,walls={'left':10.,'right':10.},door=None,keys=keys,enemies=enemies,switches=switches,x=0,y=0,z=0)
    memory={}
    for j in range(rng.randint(0,5)):
        name,category=rng.choice([('Clip','Ammo'),('Shell','Ammo'),('HealthBonus','Health'),('ArmorBonus','Armor'),('Shotgun','Weapon')])
        distance=round(rng.uniform(2,40),1);oid=index*100+j+500
        memory[oid]=dict(id=oid,name=name,category=category,distance=distance,x=distance*32,y=j*32,reachable=True)
    for j,color in enumerate(('red','blue','yellow')):
        if color in keys:continue
        distance=round(rng.uniform(5,60),1);oid=index*100+j+550
        memory[oid]=dict(id=oid,name=color.title()+'Card',category='Key',distance=distance,x=distance*32,y=0,reachable=False)
    medical=None
    if state['hp']<85 and rng.random()<.5:
        distance=round(rng.uniform(1,20),1);oid=index*100+560
        medical=dict(id=oid,name='Medikit',category='Health',distance=distance,x=distance*32,y=0,reachable=True)
        memory[oid]=medical
    state['reachable_items']={str(k):v['reachable'] for k,v in memory.items()}
    if medical and state['hp']<35 and medical['distance']<6:gold='collect_'+str(medical['id'])
    elif enemies and enemy_distance<20:gold='dodge_left_'+str(enemies[0]['id'])
    elif medical:gold='collect_'+str(medical['id'])
    elif 'yellow' in keys:gold='exit'
    else:gold='switch_'+str(min(advancing,key=lambda s:s['distance'])['id'])
    previous=rng.choice(['wait','switch','switch','attack' if enemies else 'wait','pickup' if memory else 'wait','exit'])
    if previous=='switch':
        old=rng.choice(switches);execution=dict(action='use_switch',target_id=old['id'],status='executing',movement=None)
    elif previous=='pickup':execution=dict(action='pickup',target_id=rng.choice(list(memory)),status='executing',movement=None)
    elif previous=='attack':execution=dict(action='attack',target_id=enemies[0]['id'],status='executing',movement='strafe_left')
    else:execution=dict(action=previous,target_id=None,status='executing' if previous=='exit' else 'waiting',movement=None)
    state['execution']=execution
    packet=request(state,memory,SimpleNamespace(exit={'line':1}))
    rows=list(examples(packet,{'command':gold,'weapon':'super_shotgun'},'synthetic_route_contrasts',index,0,True))
    for row in rows:row.update(synthetic=True,source_type='counterfactual_route_keys_and_enemy_distance')
    return [r for r in rows if r['kind'] in ('command','switch')]



def pairs(rng,index):
    inventory={str(i):dict(owned=int(i in (1,2,3,8)),ammo=50 if i in (3,8) else 200 if i in (2,4) else 0) for i in range(1,10)}
    lifts=[]
    for j,color in enumerate(('red','blue')):
        distance=round(rng.uniform(8,55),1);oid=index*10+j+900000
        lifts.append(dict(id=oid,name='Lift',kind='lift',distance=distance,x=distance*32,y=0,phase='call',activated=False,locked=False,route_keys=[color]))
    rows=[]
    for variant,keys,distance in [('red_owned',['red'],None),('blue_owned',['blue'],None),('near_enemy',['red'],12.),('far_enemy',['red'],42.)]:
        enemies=[] if distance is None else [dict(id=index*10+900009,name='DoomImp',distance=distance,x=distance*32,y=0,z=0,bearing=0,visible=True)]
        state=dict(hp=100,armor=100,inventory=inventory,walls={'left':10.,'right':10.},door=None,keys=keys,enemies=enemies,switches=copy.deepcopy(lifts),x=0,y=0,z=0,reachable_items={})
        state['execution']=dict(action='attack' if enemies else 'wait',target_id=enemies[0]['id'] if enemies else None,status='executing' if enemies else 'waiting',movement='strafe_left' if enemies else None)
        missing=next(l for l in lifts if l['route_keys'][0] not in keys)
        gold='dodge_left_'+str(enemies[0]['id']) if distance is not None and distance<20 else 'switch_'+str(missing['id'])
        packet=request(state,{},SimpleNamespace(exit={'line':1}))
        for row in examples(packet,{'command':gold,'weapon':'super_shotgun'},'paired_route_contrasts',index,0,True):
            if row['kind']!=('command' if enemies else 'switch'):continue
            row.update(synthetic=True,source_type='paired_key_ownership_or_enemy_distance',pair_variant=variant);rows.append(row)
    return rows


def main():
    p=argparse.ArgumentParser();p.add_argument('--replay',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.output.mkdir(exist_ok=False)
    manifest=dict(note='Offline synthetic contrasts plus development replay; no runtime policy.',source_sha256={},splits={});seen=set()
    for split,count in [('train',900),('validation',220)]:
        rng=random.Random(8641 if split=='train' else 8642);rows=[]
        for i in range(count):rows+=sample(rng,i+(0 if split=='train' else 20000))
        for i in range(100 if split=='train' else 30):rows+=pairs(rng,i+(0 if split=='train' else 20000))
        path=a.replay/(split+'.json');replay=json.loads(path.read_text());manifest['source_sha256'][str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
        for kind,cap in [('command',450),('switch',120),('item',500),('weapon',220),('movement',250),('enemy',100)]:
            choices=[r for r in replay if r['kind']==kind];rng.shuffle(choices);rows.extend(choices[:cap if split=='train' else max(25,cap//4)])
        unique=[]
        for row in rows:
            key=json.dumps([row['state'],row['question']],sort_keys=True)
            if key in seen:continue
            seen.add(key);unique.append(row)
        rng.shuffle(unique);out=a.output/(split+'.json');out.write_text(json.dumps(unique,indent=2));manifest['splits'][split]=dict(rows=len(unique),sha256=hashlib.sha256(out.read_bytes()).hexdigest(),kinds=dict(collections.Counter(r['kind'] for r in unique)))
    (a.output/'manifest.json').write_text(json.dumps(manifest,indent=2));print(json.dumps(manifest['splits'],indent=2))

if __name__=='__main__':main()
