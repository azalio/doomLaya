"""Offline demonstrations for training; never imported by the live Laya agent."""
import argparse
import collections
import copy
import json
import hashlib
import shutil
import math
import sys
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from agent import make_game, Sensors, BUTTONS
from doomlib.executor import Executor
from doomlib.mission import Mission, map_data
from doomlib.policy import request
from doomlib.items import utility, WEAPONS
from doomlib.combat import AMMO_COST


def labels(packet,s,reachable,navigator,weapon_resupply=False):
    commands=packet['commands']
    usable={int(k) for k,v in s['inventory'].items() if v['owned'] and v['ammo']>=AMMO_COST[int(k)]}
    slot=next(i for i in (6,8,3,4,2,9,1) if i in usable)
    nearest=min((e['distance'] for e in s['enemies']),default=0)
    walls=s.get('motion_clearance') or s['walls']
    clearance_margin=6 if s.get('motion_clearance') else 1.5
    weapon=next(k for k,v in packet['weapons'].items() if v==slot)
    enemies=[k for k,c in commands.items() if c['action']=='attack' and c['target']['distance']<20]
    candidates=[]
    for key,command in commands.items():
        if command['action']!='pickup':continue
        item=command['target'];category=item['category'];name=item['name'];distance=item['distance']
        if navigator.nearest((item['x'],item['y'])) not in reachable:continue
        score=utility(item,s)
        if category=='Key':score=200 if not any(name.lower().startswith(color) for color in s.get('keys',())) else 0
        elif category=='Weapon':
            score=140 if score>=100 else 0
            # Opt-in supervision preserves the frozen historical datasets.
            ammo_slot=WEAPONS.get(name)
            if weapon_resupply and not score and ammo_slot in (3,8):
                owned=s['inventory'].get(str(ammo_slot),{})
                if owned.get('owned') and owned.get('ammo',0)<20 and distance<20:score=110
        elif category=='Health':score=(180 if s['hp']<45 else 90) if s['hp']<85 and 'Bonus' not in name else 0
        elif category=='Armor':score=120 if s['armor']<60 and 'Bonus' not in name else 0
        elif category=='Ammo':
            ammo_slot=3 if 'shell' in name.lower() else (2 if name in ('Clip','ClipBox') else None)
            enough=20 if ammo_slot==3 else 70
            score=110 if ammo_slot and s['inventory'][str(ammo_slot)]['owned'] and s['inventory'][str(ammo_slot)]['ammo']<enough and distance<20 else 0
        else:score=0
        if score:candidates.append((score-distance*2,key))
    urgent=[(v,k) for v,k in candidates if commands[k]['target']['category']=='Health' and s['hp']<35 and commands[k]['target']['distance']<6]
    upgrades=[(v,k) for v,k in candidates if commands[k]['target']['category']=='Weapon' and slot in (1,2) and commands[k]['target']['distance']<5]
    nearby_switch=[k for k,c in commands.items() if c['action']=='use_switch' and c['target']['distance']<2]
    riding=[k for k,c in commands.items() if c['action']=='use_switch' and c['target'].get('kind')=='lift' and c['target'].get('phase') in ('board','ride') and c['target']['distance']<5]
    if riding:command=riding[0]
    elif s.get('door') and not s['door'].get('locked') and s['door']['distance']<2.5 and 'open_door' in commands:command='open_door'
    elif nearby_switch:command=nearby_switch[0]
    elif urgent:command=max(urgent)[1]
    elif upgrades:command=max(upgrades)[1]
    elif enemies:
        command=enemies[0]
        if AMMO_COST[slot]>0 and commands[command]['target']['distance']<5 and walls.get('back',16)>=(6 if s.get('motion_clearance') else 2.5):
            command=f"backpedal_{commands[command]['target']['id']}"
        elif AMMO_COST[slot]>0:
            current=s.get('execution',{}).get('movement')
            side=current.removeprefix('strafe_') if current in ('strafe_left','strafe_right') else None
            if side is None or walls[side]<clearance_margin:side=max(('left','right'),key=lambda k:walls[k])
            candidate=f"dodge_{side}_{commands[command]['target']['id']}"
            if walls[side]>1 and candidate in commands:command=candidate
    elif s.get('door') and not s['door'].get('locked') and s['door']['distance']<4 and 'open_door' in commands:command='open_door'
    elif candidates:command=max(candidates)[1]
    elif 'yellow' in s.get('keys',()) and 'exit' in commands:command='exit'
    elif switches:=( [(c['target']['distance'],k) for k,c in commands.items() if c['action']=='use_switch' and {728:'red',805:'blue'}.get(c['target']['id']) not in s.get('keys',())] ):
        command=min(switches)[1]
    else:command='explore'
    return {'command':command,'weapon':weapon}


def collect(seed,seconds,output,no_monsters=False,latency_ticks=0,physical_facts=False,weapon_sensor=False,map_weapons=False,reachable_items=False,decision_ticks=18,inventory_events=False):
    if decision_ticks<1 or not 0<=latency_ticks<decision_ticks:raise ValueError("latency_ticks must be smaller than positive decision_ticks")
    output=Path(output);output.mkdir(parents=True,exist_ok=False)
    source=output/'source';source.mkdir()
    files=['agent.py','doomlib/executor.py','doomlib/navigation.py','doomlib/mission.py','doomlib/policy.py','doomlib/items.py','doomlib/decision_timing.py','training/map2_teacher.py']
    if weapon_sensor:files+=['assets/weapon_sensor.acs','assets/weapon_sensor.pk3','doomlib/combat.py']
    hashes={}
    for name in files:
        dest=source/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(name,dest)
        hashes[name]=hashlib.sha256(dest.read_bytes()).hexdigest()
    (output/'config.json').write_text(json.dumps(dict(seed=seed,seconds=seconds,no_monsters=no_monsters,latency_ticks=latency_ticks,decision_ticks=decision_ticks,inventory_events=inventory_events,physical_facts=physical_facts,weapon_sensor=weapon_sensor,map_weapons=map_weapons,reachable_items=reachable_items,source_sha256=hashes),indent=2))
    args=SimpleNamespace(map='MAP02',skill=3,seed=seed,show=False,sound=False,weapon_sensor=weapon_sensor)
    game=make_game(args,no_monsters=no_monsters);game.make_action([0]*len(BUTTONS),12)
    mission=Mission(map_data(game.get_doom_game_path(),'MAP02'))
    controller=Executor(game.get_state().sectors,mission,map_weapons=map_weapons)
    sensors=Sensors(mission.data['door_sectors'],mission.data['doors'],weapon_sensor=weapon_sensor)
    last_request=-10000;last_inventory=None
    records=[];episode=0;signature=None;reachable=set();counts=collections.Counter();complete=False;pending=None
    with (output/'telemetry.jsonl').open('x') as handle:
        try:
            for tick in range(round(seconds*35)):
                if game.is_episode_finished():
                    if not game.is_player_dead():complete=True;break
                    episode+=1;game.new_episode();game.make_action([0]*len(BUTTONS),12)
                    mission=Mission(map_data(game.get_doom_game_path(),'MAP02'))
                    controller=Executor(game.get_state().sectors,mission,map_weapons=map_weapons)
                    sensors=Sensors(mission.data['door_sectors'],mission.data['doors'],weapon_sensor=weapon_sensor);signature=None;pending=None
                raw,s=sensors.read(game,tick);s.update(map='MAP02',episode=episode,tick=tick)
                mission.observe(s,raw.sectors);controller.observe(s,tick,raw.sectors)
                new=(episode,tuple(s['keys']),tuple(s['closed_remote_doors']))
                if not physical_facts and (new!=signature or s.get('floor_changes') or controller.navigator.nearest((s['x'],s['y'])) not in reachable):
                    reachable=controller.navigator.reachable((s['x'],s['y']));signature=new
                if pending and tick>=pending[0]:
                    controller.accept(pending[1],tick);pending=None
                from doomlib.decision_timing import inventory_signature,request_reason
                inventory=inventory_signature(s,episode)
                reason=request_reason(tick,last_request,decision_ticks,inventory,last_inventory,inventory_events)
                if pending is None and reason is not None:
                    if physical_facts:controller.annotate_physical_facts(s)
                    elif reachable_items:controller.annotate_reachable_items(s)
                    if physical_facts or reachable_items:reachable=controller.reachable_cache[1]
                    last_request=tick;last_inventory=inventory
                    packet=request(s,controller.known,mission);gold=labels(packet,s,reachable,controller.navigator)
                    choice=gold['command'];directive=dict(packet['commands'][choice],weapon=packet['weapons'][gold['weapon']],decision_id=tick+1,command=choice,expires_tick=tick+70)
                    if latency_ticks:pending=(tick+latency_ticks,directive)
                    else:controller.accept(directive,tick)
                    counts[directive['action']]+=1
                    for kind,q in packet['questions'].items():
                        records.append({'state':packet['state'],'question':q,'label':gold[kind],'kind':kind,
                                        'category':directive['action'] if kind=='command' else gold[kind],
                                        'source_run':output.name,'source_tick':tick,'source_seed':seed,'synthetic':False,
                                        'source_type':'mechanics_fixture_no_monsters' if no_monsters else 'offline_teacher'})
                buttons,refs=controller.act(s,tick);s.update(buttons=buttons,reflexes=refs)
                handle.write(json.dumps(s)+'\n')
                game.make_action(buttons,1)
                if tick%700==0:print(json.dumps({'seed':seed,'seconds':tick/35,'hp':s['hp'],'keys':s['keys'],'position':[s['x'],s['y']],'execution':s['execution'],'switches':[x['id'] for x in s['switches'] if x['activated']],'reachable_keys':[k for k,i in controller.known.items() if i['category']=='Key' and controller.navigator.nearest((i['x'],i['y'])) in reachable]}),flush=True)
        finally:game.close()
    (output/'examples.json').write_text(json.dumps(records,indent=2))
    summary={'no_monsters':no_monsters,'source_type':'offline_teacher','model_inference':False,'latency_ticks':latency_ticks,'decision_ticks':decision_ticks,'inventory_events':inventory_events,'physical_facts':physical_facts,'weapon_sensor':weapon_sensor,'map_weapons':map_weapons,'reachable_items':reachable_items,'map_completed':complete,'seed':seed,'seconds':tick/35,'deaths':episode,'counts':dict(counts),'examples':len(records)}
    (output/'summary.json').write_text(json.dumps(summary,indent=2));print(json.dumps(summary),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--seed',type=int,required=True);p.add_argument('--seconds',type=float,default=300);p.add_argument('--output',required=True);p.add_argument('--no-monsters',action='store_true');p.add_argument('--latency-ticks',type=int,default=0);p.add_argument('--decision-ticks',type=int,default=18);p.add_argument('--inventory-events',action='store_true');p.add_argument('--physical-facts',action='store_true');p.add_argument('--reachable-items',action='store_true');p.add_argument('--weapon-sensor',action='store_true');p.add_argument('--map-weapons',action='store_true');a=p.parse_args();collect(a.seed,a.seconds,a.output,a.no_monsters,a.latency_ticks,a.physical_facts,a.weapon_sensor,a.map_weapons,a.reachable_items,a.decision_ticks,a.inventory_events)
