"""Offline corrections of failed model decisions; never used by the live executor."""
import argparse
import collections
import copy
import hashlib
import json
import math
import random
import re
import sys
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from agent import make_game,BUTTONS
from doomlib.mission import Mission,map_data
from doomlib.executor import Executor
from doomlib.policy import request
from doomlib.decision_questions import factorize,compact_state
from doomlib.combat import WEAPON_NAMES
from doomlib.items import WEAPONS


def oracle(packet,s,nav):
    targets=packet['targets'];items=list(targets.get('item',{}).values());enemies=sorted(targets.get('enemy',{}).values(),key=lambda e:e['distance'])
    inventory=s['inventory'];usable=[slot for slot in (6,3,4,2,1) if inventory[str(slot)]['owned'] and (slot==1 or inventory[str(slot)]['ammo']>0)]
    slot=usable[0];nearest=enemies[0]['distance'] if enemies else 999
    reachable=nav.reachable((s['x'],s['y']))
    items=[item for item in items if nav.nearest((item['x'],item['y'])) in reachable]
    upgrades=[i for i in items if i['category']=='Weapon' and i['name'] in WEAPONS and not inventory[str(WEAPONS[i['name']])]['owned']]
    ammo=[i for i in items if (i['name'] in ('Clip','ClipBox') and inventory['2']['ammo']<20) or ('Shell' in i['name'] and inventory['3']['owned'] and inventory['3']['ammo']<8)]
    health=[i for i in items if i['category']=='Health' and 'Bonus' not in i['name'] and s['hp']<85]
    armor=[i for i in items if i['category']=='Armor' and 'Bonus' not in i['name'] and s['armor']<60]
    keys=[i for i in items if i['category']=='Key' and not any(i['name'].lower().startswith(k) for k in s['keys'])]
    closest=lambda values:min(values,key=lambda i:i['distance']) if values else None
    preferred=None
    if slot==1:preferred=closest(upgrades+ammo)
    if preferred is None and slot==2 and upgrades:preferred=closest(upgrades)
    if preferred is None and s['hp']<35:preferred=closest(health)
    if preferred is None:preferred=closest(keys or ammo or health or armor)
    switches=[v for v in targets.get('switch',{}).values() if {728:'red',805:'blue'}.get(v['id']) not in s['keys']]
    riding=[v for v in switches if v.get('phase') in ('board','ride') and v['distance']<5]
    command='explore'
    if riding:command='use_switch';switch=riding[0]
    elif s.get('door') and not s['door'].get('locked') and s['door']['distance']<2.5 and 'open_door' in packet['commands']:command='open_door'
    elif slot==1 and preferred:command='pickup'
    elif slot==1 and nearest>1.5:command='retreat' if 'retreat' in packet['commands'] else 'explore'
    elif slot==2 and upgrades and nearest>5:command='pickup';preferred=closest(upgrades)
    elif s['hp']<35 and health and closest(health)['distance']<6 and nearest>3:command='pickup';preferred=closest(health)
    elif nearest<20:command='attack'
    elif preferred:command='pickup'
    elif 'yellow' in s['keys'] and 'exit' in packet['commands']:command='exit'
    elif switches:command='use_switch';switch=min(switches,key=lambda v:v['distance'])
    if command not in packet['commands']:command='explore'
    gold={'command':command,'weapon':WEAPON_NAMES[slot]}
    if preferred and 'item' in packet['questions']:gold['item']=str(preferred['id'])
    if switches and 'switch' in packet['questions']:gold['switch']=str((riding[0] if riding else min(switches,key=lambda v:v['distance']))['id'])
    if command=='use_switch':gold['switch']=str(switch['id'])
    if enemies:
        gold['enemy']=str(enemies[0]['id'])
        current=s.get('execution',{}).get('movement')
        side=current.removeprefix('strafe_') if current in ('strafe_left','strafe_right') else None
        if side is None or s['walls'][side]<1.5:side=max(('left','right'),key=lambda k:s['walls'][k])
        gold['movement']='backward' if nearest<5 else 'strafe_'+side
    return gold


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run',type=Path,required=True);p.add_argument('--base-data',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    a.output.mkdir(parents=True,exist_ok=False)
    rows={r['tick']:r for r in map(json.loads,(a.run/'telemetry.jsonl').read_text().splitlines())}
    decisions=[json.loads(x) for x in (a.run/'decisions.jsonl').read_text().splitlines()]
    game=make_game(SimpleNamespace(map='MAP02',skill=3,seed=48,show=False,sound=False),no_monsters=True);game.make_action([0]*len(BUTTONS),12)
    mission=Mission(map_data(game.get_doom_game_path(),'MAP02'));nav=Executor(game.get_state().sectors,mission).navigator;game.close()
    manifest={'source_run':a.run.name,'source_sha256':{name:hashlib.sha256((a.run/name).read_bytes()).hexdigest() for name in ('config.json','decisions.jsonl','telemetry.jsonl')},'development_seed':48,'label_source':'offline corrections; split by episodes, not an independent performance test'}
    for split in ('train','validation'):
        rng=random.Random(881 if split=='train' else 882);new=collections.defaultdict(list)
        chosen=[d for index,d in enumerate(decisions) if index%2==0 and (d['episode']%2==0)==(split=='train')]
        for index,d in enumerate(chosen):
            original=rows[d['tick']]
            for variant in range(2):
                s=copy.deepcopy(original);memory={v['id']:dict(v) for v in d['packet']['targets'].get('item',{}).values()}
                if variant:
                    if index%2==0:
                        s['inventory']['2']['ammo']=0;s['inventory']['3']['ammo']=0
                    else:
                        for enemy in s['enemies']:
                            enemy['distance']=round(rng.uniform(25,40),1);enemy['x']=s['x']+enemy['distance']*32;enemy['y']=s['y']
                nav.observe(s,s['tick']);packet=factorize(request(s,memory,mission));gold=oracle(packet,s,nav)
                for kind,label in gold.items():
                    assert label in packet['questions'][kind]['criteria'],(kind,label)
                    new[kind].append(dict(state=packet['state'],question=packet['questions'][kind],label=label,kind=kind,category=gold['command'],source_run=a.run.name,source_tick=s['tick'],source_episode=s['episode'],source_type='offline_correction',synthetic=bool(variant)))
        records=[]
        for kind,candidates in new.items():
            rng.shuffle(candidates);records.extend(candidates[:(180 if kind=='command' else 90) if split=='train' else 30])
        retained=collections.defaultdict(list)
        for row in json.loads((a.base_data/(split+'.json')).read_text()):
            row=dict(row,state=compact_state(row['state']))
            if row['kind']=='movement' and row['label']=='stationary':
                match=re.search(r'left ([0-9.]+)m, right ([0-9.]+)m',row['state'])
                if match:row['label']='strafe_left' if float(match[1])>=float(match[2]) else 'strafe_right'
            retained[row['kind']].append(row)
        for kind,candidates in retained.items():
            rng.shuffle(candidates);records.extend(candidates[:(200 if kind=='command' else 100) if split=='train' else 40])
        rng.shuffle(records);target=a.output/(split+'.json');target.write_text(json.dumps(records,indent=2))
        manifest[split]={'rows':len(records),'sha256':hashlib.sha256(target.read_bytes()).hexdigest(),'groups':dict(collections.Counter(r['kind'] for r in records))};print(split,manifest[split],flush=True)
    (a.output/'manifest.json').write_text(json.dumps(manifest,indent=2))


if __name__=='__main__':main()
