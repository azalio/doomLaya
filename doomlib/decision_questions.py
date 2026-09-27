"""Independent model questions for action, target, weapon, and combat movement."""
import re

ACTION_DESCRIPTIONS={
    'attack':'Fight a visible or recently seen enemy.',
    'pickup':'Collect a useful item such as a weapon, ammunition, health, armor, or key.',
    'open_door':'Open the closed door ahead to continue the route.',
    'use_switch':'Use a switch or call, board and ride a lift to unlock the route.',
    'exit':'Go to the exit and finish the level.',
    'retreat':'Retreat from enemies without firing.',
    'explore':'Explore accessible areas for another route.',
    'wait':'Wait without moving or firing.',
}
MOVEMENTS={
    'stationary':'Stand still while aiming and firing.',
    'strafe_left':'Move left while aiming and firing. Prefer free space on the left.',
    'strafe_right':'Move right while aiming and firing. Prefer free space on the right.',
    'backward':'Move backward while aiming and firing. Keep close enemies away.',
}
TARGET_TYPES={'attack':'enemy','pickup':'item','use_switch':'switch'}
NAVIGATION_ACTIONS=('pickup','open_door','use_switch','exit','explore')


def split_command(key):
    if key.startswith('collect_'):return 'pickup',key.removeprefix('collect_'),None
    if key.startswith('switch_'):return 'use_switch',key.removeprefix('switch_'),None
    for prefix,movement in [('shoot_','stationary'),('dodge_left_','strafe_left'),('dodge_right_','strafe_right'),('backpedal_','backward')]:
        if key.startswith(prefix):return 'attack',key.removeprefix(prefix),movement
    return key,None,None


def questions(criteria):
    available={split_command(key)[0] for key in criteria}
    result={'command':dict(type='choice',instructions='Finish the level alive. Fight immediate threats, collect useful supplies and keys, open doors, activate mechanisms, and reach the exit.',
                           criteria={key:value for key,value in ACTION_DESCRIPTIONS.items() if key in available})}
    for action,kind in TARGET_TYPES.items():
        options={}
        for key,value in criteria.items():
            category,target,_=split_command(key)
            if category==action and target not in options:
                description=re.sub(r'^(Stand and fire at |Strafe (left|right) while firing at |Back away while firing at |Collect )','',value)
                options[target]=description
        if options:
            instruction={'enemy':'Choose the enemy to fight. Prefer the closest immediate threat.',
                         'item':'Choose a useful item. Get needed health, a stronger gun, ammunition for an empty gun, or a required key. Avoid unnecessary pickups.',
                         'switch':'Choose the mechanism that advances the route. Continue boarding or riding the current lift. Activate unused door switches; get missing keys.'}[kind]
            result[kind]=dict(type='choice',instructions=instruction,criteria=options)
    if 'enemy' in result:result['movement']=dict(type='choice',instructions='Choose movement while fighting. Back away from enemies closer than 5 meters; otherwise use clear space and keep the current safe strafe direction.',criteria=MOVEMENTS)
    return result


def compact_state(state):
    lines=state.splitlines()
    for i,line in enumerate(lines):
        if line.startswith('Paths to items with the current keys and floors: '):
            entries=re.findall(r'([A-Za-z]+) #(\S+) (reachable|unreachable)',line)
            lines[i]='Reachable items: '+(', '.join(name+'#'+oid for name,oid,reachable in entries if reachable=='reachable') or 'none')+'.'
    state='\n'.join(lines)
    state=re.sub(r'switch_(\d+): Activate door switch #\d+ to open a closed passage\. Distance ([0-9.]+)m\.',r'door switch #\1 \2m',state)
    state=re.sub(r'switch_(\d+): Activate floor switch #\d+ to lower the floor and open a route\. Distance ([0-9.]+)m\.',r'floor switch #\1 \2m (lowers floor)',state)
    state=re.sub(r'switch_(\d+): Call, board and ride lift #\d+ to the upper floor\. Phase: (\w+)\. Distance ([0-9.]+)m\.',r'lift #\1 phase \2 \3m',state)
    state=re.sub(r'Hostile enemies currently visible or seen in the last (?:two|[0-9.]+) seconds:','Enemies:',state).replace('Known ground items:','Items:')
    state=re.sub(r'(\w+) #(\S+) \((\w+)\) at ([0-9.]+) meters',r'\1#\2 [\3] \4m',state)
    state=re.sub(r'(\w+) #(\S+) at ([0-9.]+) meters',r'\1#\2 \3m',state)
    state=state.replace('Unreachable targets in the current area:','Unreachable:').replace(' Those commands are unavailable until the position or doors change.','')
    return state


def state_text(state,criteria):
    mechanisms=[f"{key}: {value}" for key,value in criteria.items() if split_command(key)[0]=='use_switch']
    if not mechanisms:return compact_state(state)
    lines=state.split('\n')
    lines.insert(1,'Available mechanisms: '+'; '.join(mechanisms))
    return compact_state('\n'.join(lines))


def factorize(packet):
    result=dict(packet,decision_format='factorized')
    result['state']=state_text(packet['state'],packet['questions']['command']['criteria'])
    result['questions']=questions(packet['questions']['command']['criteria'])
    result['questions']['weapon']=packet['questions']['weapon']
    result['commands']={action:dict(action=action,target=None) for action in result['questions']['command']['criteria']}
    result['targets']={kind:{} for kind in TARGET_TYPES.values() if kind in result['questions']}
    for key,command in packet['commands'].items():
        action,target,_=split_command(key)
        if action in TARGET_TYPES:result['targets'][TARGET_TYPES[action]][target]=command['target']
        else:result['commands'][action]=dict(command)
    return result


def decode(result,packet,decision_id):
    action=result['answers']['command']['choice']
    command=dict(packet['commands'][action])
    if action in TARGET_TYPES:
        kind=TARGET_TYPES[action]
        if kind=='enemy':
            from doomlib.enemy_sequences import decode_enemy
            command.update(decode_enemy(packet,result['answers'][kind]['choice']))
        else:command['target']=packet['targets'][kind][result['answers'][kind]['choice']]
    if command['action']=='attack':
        if packet.get('refresh_attack_target'):
            from doomlib.enemy_sequences import decode_enemy
            command.update(decode_enemy(packet,result['answers']['enemy']['choice']))
        movement=result['answers']['movement']['choice']
        if movement=='continue':movement=packet['current_movement']
        if movement!='stationary':command['movement']=movement
    if command['action'] in packet.get('combat_actions',('pickup',)) and packet.get('pickup_combat'):
        choice=result['answers']['combat']['choice']
        command['combat_target']=None if choice=='hold' else packet['combat_targets'][choice]
    return dict(command,weapon=packet['weapons'].get(result['answers']['weapon']['choice']),decision_id=decision_id,command=action)


def with_commitment(packet):
    """Expose the previous model goal and explicit continuation choices."""
    import copy
    from doomlib.items import weapon_slot
    result=copy.deepcopy(packet);result['decision_format']='committed'
    observed=result['observation'];current=observed.get('execution') or {}
    action=current.get('action');target_id=current.get('target_id')
    target=None;continuation=None
    if action in TARGET_TYPES:
        target=result.get('targets',{}).get(TARGET_TYPES[action],{}).get(str(target_id))
        if target:continuation=dict(action=action,target=target)
    elif action in ('open_door','exit') and action in result['commands']:
        candidate=result['commands'][action]
        if (candidate.get('target') or {}).get('id')==target_id:continuation=dict(candidate)
    goal=f"{action or 'none'} #{target_id}" if target_id is not None else (action or 'none')
    if target:goal+=f" {target['name']} {target['distance']:.1f}m"
    if target and target.get('route_keys'):
        goal+='; upper route keys: '+', '.join(target['route_keys'])
    status=current.get('status','waiting')
    if continuation and status=='executing':
        result['commands']['continue']=continuation
        result['questions']['command']['criteria']['continue']='Continue the current command: '+goal+'.'
    result['questions']['command']['instructions']+=' Continue the current goal while it remains appropriate. Change it for urgent threats, supplies, or a blocked route.'
    movement=current.get('movement')
    if movement in ('strafe_left','strafe_right','backward') and 'movement' in result['questions']:
        result['current_movement']=movement
        result['questions']['movement']['criteria']['continue']='Continue the current movement: '+movement+'.'
    enemies=list(result.get('targets',{}).get('enemy',{}).values())
    nearest=min((e['distance'] for e in enemies),default=None)
    band='none' if nearest is None else ('melee' if nearest<=1.5 else 'close' if nearest<5 else 'medium' if nearest<20 else 'far')
    health='critical' if observed['hp']<35 else ('wounded' if observed['hp']<85 else 'healthy')
    walls=observed.get('motion_clearance') or observed.get('walls') or {}
    margin=6 if observed.get('motion_clearance') else 1.5
    clearance=', '.join(side+' '+('tight' if value<margin else 'open') for side,value in walls.items() if side in ('left','right'))
    if 'back' in walls:clearance+=', back '+('tight' if walls['back']<6 else 'open')
    state=result['state']
    state=re.sub(r'The player has ([0-9.]+) health and ([0-9.]+) armor\.',r'HP \1; armor \2.',state)
    state=re.sub(r' with (\d+) ammo',r' \1 ammo',state)
    state=re.sub(r'Movement clearance: (.*?) Current combat movement: (.*?)\.',r'Clearance: \1 Movement: \2.',state)
    result['state']=f'Current command: {goal}; status {status}.\nEnemy range: {band}; health: {health}; space: {clearance}.\n'+state
    # Keep execution feedback and nearby door facts visible before the item list.
    lines=result['state'].splitlines()
    feedback=[line for line in lines if line.startswith(('A closed door','Previous command result','Door requires','Route blocked:'))]
    result['state']='\n'.join(feedback+[line for line in lines if line not in feedback])
    inventory=observed.get('inventory') or {}
    for oid,item in result.get('targets',{}).get('item',{}).items():
        description=f"{item['name']} ({item['category']}), {item['distance']:.1f}m."
        slot=weapon_slot(item['name'],inventory)
        if slot:description+=' Owned: '+('yes.' if inventory[str(slot)]['owned'] else 'no.')
        if 'reachable' in item:
            description=item['name']+'; '+('reachable' if item['reachable'] else 'unreachable')
            if slot:description+='; '+('owned' if inventory[str(slot)]['owned'] else 'not owned')
            description+=f"; {item['distance']:.1f}m."
        result['questions']['item']['criteria'][oid]=description
    return result


def without_action_continuation(packet):
    """Keep goal context while requiring an explicit action and fresh target."""
    packet['commands'].pop('continue',None)
    packet['questions']['command']['criteria'].pop('continue',None)
    packet['explicit_actions']=True
    return packet


def refresh_attack_target(packet):
    """Ask the model for a fresh enemy even when it continues fighting."""
    packet['refresh_attack_target']=True
    current=packet['commands'].get('continue')
    if current and current['action']=='attack':
        packet['questions']['command']['criteria']['continue']+=' Re-select the enemy.'
    return packet


def with_pickup_combat(packet,include_recent=False):
    """Let the model explicitly authorize a second, simultaneous combat goal."""
    packet['pickup_combat']=True
    targets={k:e for k,e in packet.get('targets',{}).get('enemy',{}).items() if include_recent or e.get('visible',True)}
    packet['combat_targets']=targets
    packet['pickup_recent_targets']=include_recent
    options={'hold':'Do not fire while collecting the selected item.'}
    options.update({k:(f"Fire at {e['name']} #{k}, {e['distance']:.1f}m away." if e.get('visible',True)
                       else f"Aim at {e['name']} #{k}, {e['distance']:.1f}m away (last seen). Fire only when visible.") for k,e in targets.items()})
    packet['questions']['combat']=dict(type='choice',instructions='Choose whether to shoot while moving to the selected item. Select an enemy to fire at, or hold fire. Keep following the selected route.',criteria=options)
    if include_recent:
        packet['questions']['combat']['instructions']='Choose an enemy to aim at while moving to the selected item, or hold. Recently seen enemies may be aimed at; fire only when they are visible. Keep following the selected route.'
    return packet


def with_navigation_combat(packet,include_recent=False):
    """Offer model-selected secondary combat for each explicit navigation action."""
    packet=with_pickup_combat(packet,include_recent=include_recent)
    packet['combat_actions']=list(NAVIGATION_ACTIONS)
    question=packet['questions']['combat']
    question['instructions']=question['instructions'].replace('moving to the selected item','executing the selected navigation command')
    question['criteria']['hold']='Do not fire while executing the selected navigation command.'
    return packet


def mask_unreachable_items(packet):
    """Remove physically impossible item commands using the observed route graph."""
    if packet.get('decision_format') not in ('factorized','committed'):
        raise ValueError('Item action mask requires factored decisions')
    items=packet.get('targets',{}).get('item',{})
    if any(type(item.get('reachable')) is not bool for item in items.values()):
        raise ValueError('Item action mask requires observed reachability for every item')
    masked={oid:item for oid,item in items.items() if not item['reachable']}
    packet['masked_unreachable_items']=list(masked.values())
    if not masked:return packet
    for oid in masked:
        packet['targets']['item'].pop(oid)
        packet['questions']['item']['criteria'].pop(oid)
    continuation=packet['commands'].get('continue',{})
    if continuation.get('action')=='pickup' and str((continuation.get('target') or {}).get('id')) in masked:
        packet['commands'].pop('continue')
        packet['questions']['command']['criteria'].pop('continue')
    if not packet['targets']['item']:
        packet['targets'].pop('item')
        packet['questions'].pop('item')
        packet['commands'].pop('pickup',None)
        packet['questions']['command']['criteria'].pop('pickup',None)
    return packet


def dependencies(packet):
    """Parameters required to execute each model-selected command."""
    result={}
    for key,command in packet['commands'].items():
        names=[];action=command['action']
        if key!='continue' and packet.get('decision_format') in ('factorized','committed') and action in TARGET_TYPES:names.append(TARGET_TYPES[action])
        if action=='attack':
            if packet.get('refresh_attack_target') and 'enemy' not in names:names.append('enemy')
            if 'movement' in packet['questions']:names.append('movement')
        if action in packet.get('combat_actions',('pickup',)) and packet.get('pickup_combat'):names.append('combat')
        result[key]=names
    return result


def with_enemy_visibility_facts(packet):
    """Describe observed visibility beside each enemy; retain every model choice."""
    import copy
    if 'enemy' not in packet['questions']:
        return packet
    result=copy.deepcopy(packet)
    criteria=result['questions']['enemy']['criteria']
    for key in criteria:
        enemy=result['targets']['enemy'][key]
        prefix='Visible now. ' if enemy.get('visible',True) else 'Not visible now; last seen. '
        criteria[key]=prefix+criteria[key]
    return result
