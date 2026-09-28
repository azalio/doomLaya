"""Experimental offline combat supervision; never imported by the live agent."""
from doomlib.combat import AMMO_COST,WEAPON_NAMES


def focused_labels(packet,state,controller,base,style,all_labels=False):
    gold=dict(base);enemies=packet.get('targets',{}).get('enemy',{})
    visible={k:e for k,e in enemies.items() if e.get('visible',True)}
    candidates=visible or enemies
    inventory=state['inventory']
    usable={int(k) for k,v in inventory.items() if v['owned'] and v['ammo']>=AMMO_COST[int(k)]}
    slot=next(k for k in (6,8,4,3,2,5,9,1) if k in usable)
    gold['weapon']=WEAPON_NAMES[slot]
    previous=controller.directive or {};previous_id=str((previous.get('target') or {}).get('id'))
    enemy=None
    if candidates:
        enemy=min(candidates,key=lambda k:candidates[k]['distance']*(.65 if candidates[k]['name'] in ('ShotgunGuy','Zombieman','ChaingunGuy') else 1)+abs(candidates[k].get('bearing',0))/30)
        if previous.get('action')=='attack' and previous_id in visible:
            urgent=candidates[enemy]['distance']<1.5 and visible[previous_id]['distance']>5
            if not urgent:enemy=previous_id
    if enemy:
        nearest=min(e['distance'] for e in candidates.values())
        clearance=controller.navigator.movement_clearance(state)
        movement='stationary'
        if style=='focused-retain':
            from training.build_map3_retained_movement import choose_retained
            movement=choose_retained(list(candidates.values()),clearance,previous.get('movement','stationary'))
        elif style=='focused-retreat':
            if nearest<12 and clearance['back']>=4:movement='backward'
            else:
                current=previous.get('movement')
                side=current.removeprefix('strafe_') if current in ('strafe_left','strafe_right') else None
                if side is None or clearance[side]<4:side=max(('left','right'),key=lambda k:clearance[k])
                if clearance[side]>=2:movement='strafe_'+side
        gold.update(enemy=enemy,movement=movement)
        # Close weapon/health pickups remain possible; other errands wait for the fight.
        item=packet.get('targets',{}).get('item',{}).get(gold.get('item')) or {}
        urgent_health=base['command']=='pickup' and item.get('category')=='Health' and item.get('distance',999)<2 and state['hp']<25
        close_upgrade=base['command']=='pickup' and item.get('category')=='Weapon' and slot in (1,2) and item.get('distance',999)<6 and nearest>3
        if (visible or nearest<20) and not (urgent_health or close_upgrade):gold['command']='attack'
    facts=state.get('recent_damage',{})
    status=state.get('execution',{})
    looking=status.get('action')=='look_back' and status.get('status')=='executing'
    needs_look=facts.get('hp_loss',0)>0 and not facts.get('looked_after_hit')
    floor_hazard=state.get('floor_hazard',{}).get('mapped_damaging_floor',False)
    if not enemies and not floor_hazard and (looking or needs_look):gold['command']='look_back'
    action=gold['command'];required=['command','weapon']
    required+= {'attack':['enemy','movement'],'pickup':['item'],'use_switch':['switch']}.get(action,[])
    if action in packet.get('combat_actions',()) and 'combat' in packet['questions']:
        combat=packet.get('combat_targets',{})
        target=next((k for k,e in combat.items() if enemy and e['id']==enemies[enemy]['id']),None)
        gold['combat']=target or 'hold';required.append('combat')
    for kind in required:
        if gold.get(kind) not in packet['questions'][kind]['criteria']:raise ValueError((kind,gold.get(kind)))
    return gold if all_labels else {k:gold[k] for k in required}


from doomlib.executor import Executor


def queued_targets(packet,first):
    enemies=packet.get('targets',{}).get('enemy',{})
    rest=sorted((k for k in enemies if k!=first),key=lambda k:enemies[k]['distance']*(.65 if enemies[k]['name'] in ('ShotgunGuy','Zombieman','ChaingunGuy') else 1))
    return [dict(enemies[k]) for k in [first]+rest]


class OfflineQueueExecutor(Executor):
    """Experimental executor only for offline teacher; follows an explicit stored order."""
    def act(self,state,tick):
        original=self.directive
        if original and original.get('action')=='attack' and original.get('target_queue'):
            observed={e['id'] for e in state['enemies']}
            available=[e for e in original['target_queue'] if e['id'] in observed]
            if available:self.directive=dict(original,target=available[0])
        try:return super().act(state,tick)
        finally:self.directive=original
