"""Offline MAP03 demonstrations; this module is never imported by the live agent."""
import argparse,collections,copy,hashlib,json,sys
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from agent import BUTTONS,Sensors,make_game
from doomlib.executor import Executor
from doomlib.mission import Mission,map_data
from doomlib.policy import request,decode
from doomlib.items import WEAPONS
from doomlib.combat import AMMO_COST
from doomlib.decision_questions import factorize,with_commitment,without_action_continuation,refresh_attack_target,with_navigation_combat,mask_unreachable_items,split_command
from doomlib.movement_questions import without_movement_continuation,with_movement_clearance
from doomlib.decision_timing import inventory_signature,request_reason


def packet_for(s,controller):
    controller.annotate_reachable_items(s)
    flat=request(s,controller.known,controller.mission)
    packet=refresh_attack_target(without_action_continuation(with_commitment(factorize(flat))))
    packet=mask_unreachable_items(with_navigation_combat(packet,include_recent=True))
    packet=without_movement_continuation(packet)
    if 'movement' in packet['questions']:
        packet=with_movement_clearance(packet,controller.navigator.movement_clearance(s))
    return packet


def labels(packet,s,controller,attack_range=20,visible_threats=False):
    inventory=s['inventory'];questions=packet['questions'];targets=packet.get('targets',{})
    usable={int(k) for k,v in inventory.items() if v['owned'] and v['ammo']>=AMMO_COST[int(k)]}
    slot=next(k for k in (6,8,3,4,2,9,1) if k in usable)
    weapon=next(k for k,v in packet['weapons'].items() if v==slot)
    gold={'weapon':weapon}
    enemies=targets.get('enemy',{})
    def threat(k):
        e=enemies[k];d=e['distance']
        if not visible_threats:return (0,d)
        priority=0 if d<2 else (1 if e.get('visible',True) else 2)
        return (priority,d*(.65 if e['name'] in ('ShotgunGuy','Zombieman','ChaingunGuy') else 1))
    enemy=min(enemies,key=threat) if enemies else None
    distance=enemies[enemy]['distance'] if enemy else float('inf')
    clearance=controller.navigator.movement_clearance(s)
    movement='stationary'
    if enemy:
        if distance<5 and clearance.get('back',0)>=6:movement='backward'
        else:
            current=s.get('execution',{}).get('movement')
            side=current.removeprefix('strafe_') if current in ('strafe_left','strafe_right') else None
            if side is None or clearance[side]<6:side=max(('left','right'),key=lambda k:clearance[k])
            if clearance[side]>1:movement='strafe_'+side
        gold.update(enemy=enemy,movement=movement)
    candidates=[]
    for key,item in targets.get('item',{}).items():
        if not item.get('reachable'):continue
        name=item['name'];category=item['category'];d=item['distance'];score=0
        if category=='Key':score=200
        elif category=='Health' and 'Bonus' not in name and s['hp']<85:score=220 if s['hp']<45 else 90
        elif category=='Armor' and 'Bonus' not in name and s['armor']<60:score=150
        elif category=='Weapon':
            k=WEAPONS.get(name);entry=inventory.get(str(k),{})
            if k in (3,4,6,8) and not entry.get('owned'):score=180 if slot in (1,2) else 100
            elif k in (3,8) and entry.get('owned') and entry['ammo']<20 and d<20:score=110
        elif category=='Ammo':
            k=3 if 'shell' in name.lower() else (2 if name in ('Clip','ClipBox') else None)
            if k and inventory[str(k)]['owned'] and inventory[str(k)]['ammo']<(20 if k==3 else 70) and d<20:score=110
        if score>2*d:candidates.append((score-2*d,key))
    item=max(candidates)[1] if candidates else None
    if item:gold['item']=item
    mechanisms=targets.get('switch',{})
    reachable=controller.reachable_cache[1]
    def adds_upper_route(lift):
        if controller.navigator.nearest(lift['approach']) not in reachable:return False
        nav=copy.copy(controller.navigator);nav.sector_heights=list(nav.sector_heights);nav.floors=dict(nav.floors)
        affected=set()
        for sector in lift['sectors']:
            nav.sector_heights[sector]=lift['upper_floor'];affected.update(nav.sector_cells.get(sector,()))
        for node in affected:nav.floors[node]=max(nav.sector_heights[i] for i in nav.body_sectors[node])
        added=nav.reachable(lift['board'])-reachable
        exits=controller.mission.data['exits']
        if any(not e['secret'] and nav.nearest(e['approach']) in added for e in exits):return True
        return any(m['id']!=lift['id'] and not m['activated'] and not m['locked'] and nav.nearest(m['approach']) in added for m in s['switches'])
    def needed(m):
        if m.get('kind')!='lift':return True
        if set(m.get('route_keys',()))-set(s['keys']):return True
        return adds_upper_route(m)
    switches=[(m['distance'],key) for key,m in mechanisms.items() if needed(m)]
    current=s.get('execution',{})
    riding=[key for key,m in mechanisms.items() if m.get('kind')=='lift' and m.get('phase') in ('board','ride') and m['distance']<5 and current.get('action')=='use_switch' and str(current.get('target_id'))==key]
    exit_controls=[(m['distance'],k) for k,m in mechanisms.items() if m.get('route_exit')]
    switch=riding[0] if riding else (min(exit_controls)[1] if set(s['keys'])>={'blue','red','yellow'} and exit_controls else min(switches)[1] if switches else None)
    if switch:gold['switch']=switch
    urgent=[(score,key) for score,key in candidates if targets['item'][key]['category']=='Health' and s['hp']<35 and targets['item'][key]['distance']<6]
    upgrades=[(score,key) for score,key in candidates if targets['item'][key]['category']=='Weapon' and slot in (1,2) and targets['item'][key]['distance']<10]
    door=packet['commands'].get('open_door',{}).get('target') or {}
    blocked_door='A closed door blocks movement' in s.get('execution',{}).get('detail','') and 'open_door' in packet['commands']
    if blocked_door:action='open_door'
    elif riding:action='use_switch'
    elif urgent:action='pickup';gold['item']=max(urgent)[1]
    elif upgrades and distance>=3:action='pickup';gold['item']=max(upgrades)[1]
    elif enemy and distance<attack_range:action='attack'
    elif door.get('distance',999)<4:action='open_door'
    elif candidates:action='pickup'
    elif 'exit' in packet['commands'] and set(s['keys'])>={'blue','red','yellow'}:action='exit'
    elif switch:action='use_switch'
    elif 'exit' in packet['commands']:action='exit'
    else:action='explore'
    gold['command']=action
    if 'combat' in questions:
        combat=[(t['distance'],key) for key,t in packet['combat_targets'].items() if t['distance']<attack_range]
        gold['combat']=min(combat)[1] if combat else 'hold'
    required=['command','weapon']
    required+= {'attack':['enemy','movement'],'pickup':['item'],'use_switch':['switch']}.get(action,[])
    if action in packet.get('combat_actions',()) and 'combat' in questions:required.append('combat')
    for kind in required:
        if gold[kind] not in questions[kind]['criteria']:raise ValueError((kind,gold[kind],questions[kind]))
    return {k:gold[k] for k in required}


def collect(output,seed,seconds,latency_ticks,attack_range=20,enemy_memory_ticks=70,visible_threats=False,no_monsters=False,combat_style='original',attack_turn_rate=9,max_deaths=None,attack_queue=False,floor_facts=False):
    output.mkdir(parents=True,exist_ok=False)
    source=output/'source';source.mkdir()
    names=['agent.py',str(Path(__file__).relative_to(Path.cwd()))]+[str(p) for p in Path('doomlib').glob('*.py')]
    hashes={}
    for name in names:
        p=Path(name);dest=source/p;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(p.read_bytes());hashes[name]=hashlib.sha256(p.read_bytes()).hexdigest()
    if combat_style!='original' or attack_queue:
        extra=Path('training/map3_focused_teacher.py');dest=source/extra;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(extra.read_bytes());hashes[str(extra)]=hashlib.sha256(extra.read_bytes()).hexdigest()
    if combat_style=='focused-retain':
        extra=Path('training/build_map3_retained_movement.py');dest=source/extra;dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(extra.read_bytes());hashes[str(extra)]=hashlib.sha256(extra.read_bytes()).hexdigest()
    config=dict(floor_facts=floor_facts,attack_queue=attack_queue,combat_style=combat_style,attack_turn_rate=attack_turn_rate,max_deaths=max_deaths,source_type='offline_teacher',model_inference=False,map='MAP03',seed=seed,skill=3,seconds=seconds,latency_ticks=latency_ticks,decision_ticks=18,attack_range=attack_range,enemy_memory_ticks=enemy_memory_ticks,visible_threats=visible_threats,no_monsters=no_monsters,source_sha256=hashes)
    (output/'config.json').write_text(json.dumps(config,indent=2))
    game=make_game(SimpleNamespace(map='MAP03',skill=3,seed=seed,show=False,sound=False,weapon_sensor=True),no_monsters=no_monsters)
    idle=[0.]*len(BUTTONS);episode=-1;counts=collections.Counter();completed=False;last_request=-10000;last_inventory=None;pending=None
    def restart():
        game.make_action(idle,12)
        mission=Mission(map_data(game.get_doom_game_path(),'MAP03'))
        from training.map3_focused_teacher import OfflineQueueExecutor
        executor=OfflineQueueExecutor if attack_queue else Executor
        c=executor(game.get_state().sectors,mission,map_weapons=True,mechanism_facts=True,attack_turn_rate=attack_turn_rate)
        if floor_facts:
            from doomlib.floor_hazards import FloorHazards
            c.floor_hazards=FloorHazards(game.get_doom_game_path(),'MAP03',game.get_state().sectors)
        return c,Sensors(mission.data['door_sectors'],mission.data['doors'],weapon_sensor=True,enemy_memory_ticks=enemy_memory_ticks)
    from doomlib.look_questions import DamageHistory,with_look_action
    from training.map3_focused_teacher import focused_labels,queued_targets
    damage=DamageHistory()
    controller,sensors=restart();episode=0
    with (output/'examples.jsonl').open('x') as examples,(output/'telemetry.jsonl').open('x') as telemetry:
        try:
            for tick in range(round(seconds*35)):
                if game.is_episode_finished():
                    if not game.is_player_dead():completed=True;break
                    episode+=1
                    if max_deaths is not None and episode>=max_deaths:break
                    game.new_episode();controller,sensors=restart();pending=None;last_request=-10000;last_inventory=None
                raw,s=sensors.read(game,tick);s.update(map='MAP03',episode=episode,tick=tick,seconds=tick/35)
                controller.mission.observe(s,raw.sectors);controller.observe(s,tick,raw.sectors)
                s['recent_damage']=damage.observe(s,tick,episode)
                if floor_facts:s['floor_hazard']=controller.floor_hazards.observe(s,raw.sectors)
                if pending and tick>=pending[0]:controller.accept(pending[1],tick);pending=None
                signature=inventory_signature(s,episode,include_ammo=True)
                if pending is None and request_reason(tick,last_request,18,signature,last_inventory,True):
                    packet=packet_for(s,controller);gold=labels(packet,s,controller,attack_range,visible_threats)
                    if combat_style!='original':
                        packet=with_look_action(packet,s['recent_damage'])
                        gold=focused_labels(packet,s,controller,gold,combat_style)
                    result={'answers':{k:{'choice':v} for k,v in gold.items()}}
                    directive=decode(result,packet,tick+1);directive['expires_tick']=tick+70
                    if attack_queue and directive['action']=='attack':directive['target_queue']=queued_targets(packet,gold['enemy'])
                    pending=(tick+latency_ticks,directive);last_request=tick;last_inventory=signature;counts[gold['command']]+=1
                    for kind,label in gold.items():
                        examples.write(json.dumps(dict(kind=kind,label=label,category=gold['command'],state=packet['state'],question=packet['questions'][kind],source_run=output.name,source_tick=tick,source_episode=episode,source_type='mechanics_fixture_no_monsters' if no_monsters else 'offline_teacher',synthetic=False))+'\n')
                buttons,refs=controller.act(s,tick);s.update(buttons=buttons,reflexes=refs);telemetry.write(json.dumps(s)+'\n');game.make_action(buttons,1)
                if tick%700==0:print(json.dumps({k:s.get(k) for k in ('seconds','episode','hp','armor','keys','kills','x','y','execution','navigation')}),flush=True)
        finally:game.close()
    summary=dict(config,map_completed=completed,game_seconds=tick/35,deaths=episode,counts=dict(counts))
    (output/'summary.json').write_text(json.dumps(summary,indent=2));print(json.dumps(summary),flush=True)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--seed',type=int,default=54);p.add_argument('--seconds',type=int,default=1200);p.add_argument('--latency-ticks',type=int,default=12);p.add_argument('--attack-range',type=float,default=20);p.add_argument('--enemy-memory-ticks',type=int,default=70);p.add_argument('--visible-threats',action='store_true');p.add_argument('--no-monsters',action='store_true');p.add_argument('--combat-style',choices=['original','focused-stationary','focused-retreat','focused-retain'],default='original');p.add_argument('--attack-turn-rate',type=int,choices=[9,18,36],default=9);p.add_argument('--max-deaths',type=int);p.add_argument('--attack-queue',action='store_true');p.add_argument('--floor-facts',action='store_true');a=p.parse_args();collect(a.output,a.seed,a.seconds,a.latency_ticks,a.attack_range,a.enemy_memory_ticks,a.visible_threats,a.no_monsters,a.combat_style,a.attack_turn_rate,a.max_deaths,a.attack_queue,a.floor_facts)
