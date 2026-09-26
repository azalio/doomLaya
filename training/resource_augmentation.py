"""Offline factual rendering and label-preserving order/ID augmentation."""
import copy
import re
from doomlib.resource_questions import describe
from doomlib.combat import WEAPON_NAMES


def resource_facts(row):
    row=copy.deepcopy(row)
    if row['kind']!='item':return row
    state=row['state'];hp=re.search(r'HP ([0-9.]+); armor ([0-9.]+)',state)
    if hp is None:raise ValueError('Resource state has no HP/armor')
    inventory={str(i):dict(owned=0,ammo=0) for i in range(1,10)}
    line=next(v for v in state.splitlines() if v.startswith('Inventory:'))
    names={name:str(slot) for slot,name in WEAPON_NAMES.items()}
    for name,ammo in re.findall(r'(\w+)(?: with)? ([0-9.]+) ammo',line):
        slot=names[name];inventory[slot]=dict(owned=1,ammo=float(ammo))
    for a,b in (('2','4'),('3','8'),('6','7')):
        ammo=max(inventory[a]['ammo'],inventory[b]['ammo']);inventory[a]['ammo']=inventory[b]['ammo']=ammo
    observation=dict(hp=float(hp[1]),armor=float(hp[2]),inventory=inventory)
    criteria={}
    for oid,value in row['question']['criteria'].items():
        name=value.split(';')[0];distance=re.search(r'([0-9.]+)m',value)
        category=('Weapon' if name in ('Shotgun','SuperShotgun','Chaingun','RocketLauncher','PlasmaRifle','BFG9000','Chainsaw') else 'Health' if name in ('Medikit','Stimpack','HealthBonus') else 'Armor' if 'Armor' in name else 'Key' if 'Card' in name or 'Skull' in name else 'Ammo')
        if not distance or 'reachable' not in value:raise ValueError('Unsupported item description: '+value)
        criteria[oid]=describe(dict(name=name,category=category,distance=float(distance[1]),reachable='unreachable' not in value),observation)
    row['question']['criteria']=criteria
    return row


def shuffle_and_rename(row,rng):
    row=copy.deepcopy(row);state=row['state'];question=row['question']
    ids=list(dict.fromkeys(re.findall(r'#([A-Za-z0-9_]+)',state)))
    if row['kind'] in ('item','enemy','switch','combat'):
        ids+=list(k for k in question['criteria'] if k not in ids and k!='hold')
    labels=rng.sample(range(10000,1000000),len(ids));mapping={oid:str(label) for oid,label in zip(ids,labels)}
    def replace(text):return re.sub(r'#([A-Za-z0-9_]+)',lambda m:'#'+mapping[m[1]],text)
    row['state']=replace(state)
    options=[(mapping.get(k,k),replace(v)) for k,v in question['criteria'].items()];rng.shuffle(options)
    question['criteria']=dict(options);row['label']=mapping.get(row['label'],row['label'])
    row['object_ids_augmented']=True;row['option_order_augmented']=True
    assert row['label'] in question['criteria']
    return row
