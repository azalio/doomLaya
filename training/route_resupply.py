"""Offline resupply supervision based on the original successful map teachers."""
import re
from doomlib.combat import AMMO_COST
from doomlib.items import WEAPONS


def labels(packet):
    observation=packet['observation'];inventory=observation['inventory']
    hp=observation['hp'];armor=observation.get('armor',0)
    targets=packet.get('targets',{});items=targets.get('item',{})
    options=packet['questions']['command']['criteria']
    usable={int(k) for k,v in inventory.items() if v['owned'] and v['ammo']>=AMMO_COST[int(k)]}
    strong=bool(usable.intersection({3,4,5,6,7,8}))
    resources=[];keys=[];urgent=[]
    for key,item in items.items():
        if not item.get('reachable'):continue
        name=item['name'];category=item['category'];distance=item['distance'];score=0
        if category=='Key':keys.append((200-distance,key))
        elif category=='Health' and 'Bonus' not in name and hp<85:
            score=(220 if hp<45 else 90)-2*distance
            if hp<35 and distance<6:urgent.append((score,key))
        elif category=='Armor' and 'Bonus' not in name and armor<60:score=150-2*distance
        elif category=='Weapon':
            slot=WEAPONS.get(name);entry=inventory.get(str(slot),{})
            if slot in (3,4,6,8) and not entry.get('owned'):score=(180 if not strong else 100)-2*distance
            elif slot in (3,8) and entry.get('owned') and entry['ammo']<20 and distance<20:score=110-2*distance
        elif category=='Ammo':
            slot=3 if 'shell' in name.lower() else 2 if name in ('Clip','ClipBox') else None
            if slot and inventory[str(slot)]['owned'] and distance<20:
                if inventory[str(slot)]['ammo']<(20 if slot==3 else 70):score=110-2*distance
        if score>0:resources.append((score,key))
    current=observation.get('execution') or {};mechanisms=targets.get('switch',{})
    riding=any(m.get('kind')=='lift' and m.get('phase') in ('board','ride') and m['distance']<5 and current.get('action')=='use_switch' and str(current.get('target_id'))==key for key,m in mechanisms.items())
    enemies=list(targets.get('enemy',{}).values())
    threat=any(e['distance']<20 for e in enemies)
    nearest=min((e['distance'] for e in enemies),default=float('inf'))
    upgrade=[r for r in resources if items[r[1]]['category']=='Weapon' and not strong and items[r[1]]['distance']<5]
    door=packet.get('commands',{}).get('open_door',{}).get('target') or {}
    match=re.search(r'^Collected keys: (.*)\.',packet['state'],re.M)
    collected=set(match[1].replace(',','').split()) if match else set()
    chosen=None
    if 'open_door' in options and 'A closed door blocks movement' in current.get('detail',''):action,category='open_door','blocked_door'
    elif riding:action,category='use_switch','continue_lift'
    elif urgent:action,category='pickup','urgent_health';chosen=max(urgent)[1]
    elif upgrade and nearest>=3:action,category='pickup','close_weapon';chosen=max(upgrade)[1]
    elif threat and 'attack' in options:action,category='attack','fight'
    elif 'open_door' in options and door.get('distance',999)<4:action,category='open_door','nearby_door'
    elif keys:action,category='pickup','missing_key';chosen=max(keys)[1]
    elif resources:action,category='pickup','needed_supply';chosen=max(resources)[1]
    elif mechanisms and any(m.get('route_exit') and not m.get('activated') for m in mechanisms.values()):action,category='use_switch','exit_platform'
    elif 'exit' in options and collected>={'blue','red','yellow'}:action,category='exit','all_keys_exit'
    elif mechanisms and 'use_switch' in options:action,category='use_switch','continue_route'
    elif 'exit' in options:action,category='exit','available_exit'
    else:action,category='explore','other_route'
    result=[('command',action,'route_'+category)] if action in options else []
    if chosen is not None:result.append(('item',chosen,'route_'+items[chosen]['category'].lower()))
    return result
