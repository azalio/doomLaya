"""Offline, seeded physical-observation augmentation with the existing route labeler."""
import copy
import random
from doomlib.combat import WEAPON_NAMES
from doomlib.command_facts import stable_command_facts_input
from doomlib.decision_questions import ACTION_DESCRIPTIONS
from doomlib.numeric_command import features
from training.route_priority import labels


def examples(item_categories, count, seed, labeler=labels, include_items=False, broad_inventory=False, broad_mechanisms=False):
    rng=random.Random(seed)
    names=sorted(item_categories)
    for index in range(count):
        hp=rng.randrange(1,201 if broad_inventory else 102);armor=rng.choice((0,0,rng.randrange(1,201 if broad_inventory else 151)))
        inventory={str(slot):dict(owned=int(slot in (1,2) or rng.random() < (0.65 if slot==3 else 0.08)),ammo=0) for slot in WEAPON_NAMES}
        limits=[((2,4),201),((3,8),51),((5,),51),((6,7),301)] if broad_inventory else [((2,4),100),((3,8),30),((5,),25),((6,7),120)]
        for slots,limit in limits:
            ammo=rng.choice((0,1,2,3,4,rng.randrange(limit)))
            for slot in slots:inventory[str(slot)]['ammo']=ammo
        items={}
        for item_index,name in enumerate(rng.sample(names,rng.randrange(0,min(len(names),9)+1))):
            if item_categories[name]=='Key' and rng.random()<0.8:continue
            distance=round(rng.choice((rng.uniform(.1,12),rng.uniform(12,80))),1)
            items[str(item_index)]=dict(name=name,category=item_categories[name],distance=distance,reachable=True)
        enemies={str(i):dict(distance=round(rng.uniform(.1,60),1),visible=rng.random()<.5) for i in range(rng.choices((0,1,2,3),weights=(6,3,1,1))[0])}
        mechanism_count=rng.choices(tuple(range(13)),weights=(2,6,2,1,1,1,1,1,1,1,1,1,1))[0] if broad_mechanisms else rng.choices((0,1,2,3),weights=(2,6,2,1))[0]
        mechanisms={str(i+100):dict(kind=rng.choice(('lift','door switch','floor switch')),phase=rng.choice(('call','board','ride')),distance=round(rng.uniform(.1,30),1),route_exit=rng.random()<.04,activated=False) for i in range(mechanism_count)}
        current={}
        if mechanisms and rng.random()<.4:
            key=rng.choice(list(mechanisms));current=dict(action='use_switch',target_id=key)
        door=round(rng.uniform(.1,12),1) if rng.random()<.35 else None
        blocked=door is not None and rng.random()<.2
        if blocked:current['detail']='A closed door blocks movement'
        keys=rng.sample(('red','blue','yellow'),rng.randrange(4))
        options={'explore','wait','retreat'}
        if items:options.add('pickup')
        if enemies:options.add('attack')
        if mechanisms:options.add('use_switch')
        if door is not None:options.add('open_door')
        if rng.random()<.9:options.add('exit')
        question=dict(type='choice',instructions='Finish the level alive.',criteria={k:v for k,v in ACTION_DESCRIPTIONS.items() if k in options})
        lines=[f'HP {hp}; armor {armor}.','Inventory: '+'; '.join(f'{WEAPON_NAMES[int(k)]} {v["ammo"]} ammo' for k,v in inventory.items() if v['owned'])+'.',
               'Collected keys: '+(', '.join(keys) or 'none')+'.',
               'Reachable items: '+(', '.join(v['name']+'#'+k for k,v in items.items()) or 'none')+'.']
        if items:lines.append('Items: '+'; '.join(f'{v["name"]}#{k} [{v["category"]}] {v["distance"]:.1f}m' for k,v in items.items())+'.')
        if enemies:lines.append('Enemies: '+'; '.join(f'DoomImp#{k} {v["distance"]:.1f}m ({"visible" if v["visible"] else "last seen"})' for k,v in enemies.items())+'.')
        if mechanisms:
            entries=[]
            for k,v in mechanisms.items():
                phase=' phase '+v['phase'] if v['kind']=='lift' else ''
                entries.append(f'{v["kind"]} #{k}{phase} {v["distance"]:.1f}m'+(' Exit platform.' if v['route_exit'] else ''))
            lines.append('Available mechanisms: '+'; '.join(entries))
        if current.get('action'):lines.append('Current command: use_switch #'+current['target_id']+'; status executing.')
        if door is not None:lines.append(f'A closed door is {door:.1f} meters away.')
        if blocked:lines.append('Previous command result: A closed door blocks movement; choose open_door to open it.')
        packet=dict(state='\n'.join(lines),questions={'command':question},observation=dict(hp=hp,armor=armor,inventory=inventory,execution=current),
            targets=dict(item=items,enemy=enemies,switch=mechanisms),commands={'open_door':{'target':{'distance':door}}} if door is not None else {})
        targets=labeler(packet)
        label=next((value for kind,value,_ in targets if kind=='command'),None)
        if label is None:continue
        state,q=stable_command_facts_input(packet['state'],question)
        result=dict(state=state,question=q,label=label,synthetic=True,source_seed=seed,source_index=index)
        if include_items:
            result['packet']=packet
            result['item_label']=next((value for kind,value,_ in targets if kind=='item'),None)
        yield result
