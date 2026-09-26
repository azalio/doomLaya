"""Observation-to-question formatting; only model responses select commands."""
import math
from combat import WEAPON_NAMES,AMMO_COST

ACTIONS={k:k for k in ('attack','pickup','open_door','use_switch','exit','retreat','explore','wait')}
WEAPON_DESCRIPTIONS={1:'Fists: melee, no ammunition needed.',2:'Pistol: use only when stronger guns have no ammo.',3:'Shotgun: prefer this powerful gun to the pistol when shells are available.',
                     4:'Chaingun: rapid bullet fire.',5:'Rocket launcher: powerful, dangerous at close range.',
                     6:'Plasma rifle: powerful rapid fire.',7:'BFG: powerful, consumes 40 cells per shot.'}


def request(s, memory, mission):
    enemies=s['enemies'][:3]
    failures=s.get('target_failures',{})
    available=sorted((i for i in memory.values() if str(i['id']) not in failures),key=lambda i:i['distance'])
    important=[i for i in available if i['category'] in ('Key','Weapon') or (i['category'] in ('Health','Armor') and 'Bonus' not in i['name'])]
    items=important[:10]+[i for i in available if i not in important][:10]
    lines=[f"The player has {s['hp']:.0f} health and {s['armor']:.0f} armor.",
           'Inventory: '+ '; '.join(f"{WEAPON_NAMES[int(k)]} with {v['ammo']} ammo" for k,v in s['inventory'].items() if v['owned'])+'.']
    if 'walls' in s:lines.append(f"Movement clearance: left {s['walls']['left']:.1f}m, right {s['walls']['right']:.1f}m. Current combat movement: {s.get('execution',{}).get('movement') or 'stationary'}.")
    if s.get('motion_clearance'):
        lines.insert(0,'Body clearance: '+', '.join(f"{side} {value:.1f}m" for side,value in s['motion_clearance'].items())+'.')
    if s.get('reachable_items') is not None:
        lines.insert(0,'Paths to items with the current keys and floors: '+ '; '.join(f"{i['name']} #{i['id']} {'reachable' if i.get('reachable') else 'unreachable'}" for i in items)+'.')
    if 'keys' in s:lines.append('Collected keys: '+(', '.join(s['keys']) or 'none')+'.')
    if s.get('command_failures'):lines.append('Route blocked: '+ '; '.join(s['command_failures'].values())+'. Explore accessible areas for keys and another route.')
    if enemies:
        lines.append('Hostile enemies currently visible or seen in the last two seconds: '+ '; '.join(f"{e['name']} #{e['id']} at {e['distance']:.1f} meters ({'visible' if e.get('visible',True) else 'last seen'})" for e in enemies)+'.')
    else:lines.append('No enemies visible or seen in the last two seconds.')
    if items:lines.append('Known ground items: '+ '; '.join(f"{i['name']} #{i['id']} ({i['category']}) at {i['distance']:.1f} meters" for i in items)+'.')
    if failures:lines.append('Unreachable targets in the current area: '+', '.join('#'+key for key in failures)+'. Those commands are unavailable until the position or doors change.')
    commands={}
    criteria={}
    def add(key,description,action,target=None,movement=None):
        criteria[key]=description
        commands[key]={'action':action,'target':target}
        if movement:commands[key]['movement']=movement
    for e in enemies:
        add(f"shoot_{e['id']}",f"Stand and fire at {e['name']} #{e['id']}, {e['distance']:.1f}m away.",'attack',dict(e))
        add(f"backpedal_{e['id']}",f"Back away while firing at {e['name']} #{e['id']}, {e['distance']:.1f}m away.",'attack',dict(e),'backward')
        for side in ('left','right'):
            add(f"dodge_{side}_{e['id']}",f"Strafe {side} while firing at {e['name']} #{e['id']}, {e['distance']:.1f}m away.",'attack',dict(e),'strafe_'+side)
    for i in items:
        add(f"collect_{i['id']}",f"Collect {i['name']} #{i['id']} ({i['category']}), {i['distance']:.1f}m away. {s.get('target_failures',{}).get(str(i['id']), '')}",'pickup',dict(i))
    d=s['door']
    if d:
        lines.append(f"A closed door is {d['distance']:.1f} meters away.")
        if d.get('required_key'):lines.append('Door requires the '+d['required_key']+' key. '+('Cannot open it until the key is collected.' if d.get('locked') else 'The player has this key.'))
        if not d.get('locked'):add('open_door','Approach and open the closed door.','open_door',dict(d))
    for switch in s.get('switches',()):
        if switch['activated'] or switch['locked'] or str(switch['id']) in failures:continue
        description=(f"Call, board and ride lift #{switch['id']} to the upper floor. Phase: {switch.get('phase','call')}." if switch.get('kind')=='lift'
                     else f"Activate door switch #{switch['id']} to open a closed passage.")
        description+=f" Distance {switch['distance']:.1f}m."
        if switch.get('route_keys'):
            description+=' Upper route keys: '+', '.join(color+(' (collected)' if color in s.get('keys',()) else ' (missing)') for color in switch['route_keys'])+'.'
        add(f"switch_{switch['id']}",description,'use_switch',dict(switch))
    if mission and mission.exit and 'exit' not in s.get('command_failures',{}):
        add('exit','No immediate threat or needed supplies: reach the exit to complete the level.','exit')
    if enemies:add('retreat','Back away from the enemies without firing.','retreat')
    add('explore','Search unknown areas when the current route is blocked.','explore')
    add('wait','Stay still without firing.','wait')
    execution=s.get('execution',{})
    if execution.get('status') in ('blocked','unavailable','arrived'):
        lines.append('Previous command result: '+execution.get('detail',execution['status'])+'.')
    weapons={WEAPON_NAMES[int(k)]:int(k) for k,v in s['inventory'].items() if v['owned']}
    nearest=min((e['distance'] for e in enemies),default=None)
    weapon_options={}
    for key,slot in weapons.items():
        ammo=s['inventory'][str(slot)]['ammo']
        loaded=ammo>=AMMO_COST[slot]
        reaches=nearest is not None and (AMMO_COST[slot]>0 or nearest<=1.5)
        kind='Melee only, range 1.5m' if AMMO_COST[slot]==0 else ('Super shotgun: stronger than the shotgun, uses two shells' if slot==8 else 'Powerful ranged gun' if slot in (3,4,5,6,7) else 'Basic ranged gun')
        weapon_options[key]=f"{kind}. Loaded: {'yes' if loaded else 'no'}. Can hit visible enemies from here: {'yes' if loaded and reaches else 'no'}. Ammo: {ammo}."
    weapon_options['keep']='Keep the current weapon.'
    q={'command':{'type':'choice','instructions':'Finish the level alive. Fight visible threats, get needed supplies, open blocking doors, activate switches to unlock passages, reach exit. Avoid unreachable targets and unnecessary detours.','criteria':criteria},
       'weapon':{'type':'choice','instructions':'Choose an effective weapon. Use a loaded gun for ranged enemies. Prefer shotgun to pistol when both are loaded. Use melee when there is no usable gun.','criteria':weapon_options}}
    if '8' in s['inventory']:q['weapon']['instructions']+=' Prefer a loaded super shotgun to the ordinary shotgun.'
    return {'state':'\n'.join(lines),'questions':q,'commands':commands,'weapons':weapons,
            'observation':{k:s.get(k) for k in ('hp','armor','inventory','walls','execution','motion_clearance','reachable_items')}}


def decode(result, packet, decision_id):
    if packet.get('decision_format') in ('factorized','committed'):
        from decision_questions import decode as decode_factorized
        return decode_factorized(result,packet,decision_id)
    chosen=result['answers']['command']['choice']
    weapon=result['answers']['weapon']['choice']
    return dict(packet['commands'][chosen],weapon=packet['weapons'].get(weapon),decision_id=decision_id,command=chosen)
