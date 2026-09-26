"""Проверка боевого поведения и полезного сбора по реальному E2E."""
from collections import Counter
import argparse
import json
from pathlib import Path

from doomlib.items import utility
from doomlib import ensure_utf8_stdio

ensure_utf8_stdio()


def analyze(rows):
    aim_conflicts=lost_targets=bad_pickups=0
    combat_ticks=shots=strong_shots=0
    weapon_delay=max_weapon_delay=0
    gains=Counter()
    weapons=Counter()
    previous=None
    for row in rows:
        combat=row.get('combat',{})
        mode=combat.get('mode')
        weapons[row['weapon']]+=1
        if mode=='combat':
            combat_ticks+=1
            expected=max(-9,min(9,combat['target_bearing']))
            aim_conflicts+=abs(row['buttons'][4]-expected)>.01
            if previous and previous['episode']==row['episode']:
                old=previous.get('combat',{}).get('target_id')
                alive=any(e['id']==old for e in row['enemies'])
                if old is not None and alive and row['kills']==previous['kills'] and combat['target_id']!=old:
                    lost_targets+=1
        if row['buttons'][5]:
            shots+=1
            strong_shots+=row['weapon'] in (3,4,5,6,7)
        preferred=combat.get('preferred_weapon',row['weapon'])
        if preferred>=3 and row['weapon']<=2:
            weapon_delay+=1
            max_weapon_delay=max(max_weapon_delay,weapon_delay)
        else:weapon_delay=0
        resource=row.get('resource',{})
        gains.update(resource.get('gains',{}))
        if mode in ('pickup','urgent_health'):
            target=resource.get('target')
            bad_pickups+=not target or utility(target,row)<=0
        previous=row
    hits=sum(max(0,b.get('hitcount',0)-a.get('hitcount',0)) for a,b in zip(rows,rows[1:]) if a['episode']==b['episode'])
    return {'combat_ticks':combat_ticks,'attack_ticks':shots,'strong_weapon_attack_ticks':strong_shots,
            'actual_hits':hits,'aim_overridden_ticks':aim_conflicts,'abandoned_visible_target_ticks':lost_targets,
            'max_upgrade_delay_seconds':round(max_weapon_delay/35,2),'useless_pickup_target_ticks':bad_pickups,
            'resource_gains':dict(gains),'weapon_ticks':dict(weapons)}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run')
    args=parser.parse_args()
    root=Path(args.run)
    config=json.loads((root/'config.json').read_text())
    rows=[json.loads(l) for l in (root/'telemetry.jsonl').read_text().splitlines()]
    result=analyze(rows)
    errors=[]
    if config['args']['dry']:errors.append('Behavior acceptance requires real Laya')
    for field in ('aim_overridden_ticks','abandoned_visible_target_ticks','useless_pickup_target_ticks'):
        if result[field]:errors.append(field)
    if result['max_upgrade_delay_seconds']>1.5:errors.append('Better weapon was left unused too long')
    if not result['actual_hits']:errors.append('No confirmed hits')
    if not result['strong_weapon_attack_ticks']:errors.append('Stronger weapon was not used to fire')
    if not result['resource_gains']:errors.append('No resource gains')
    print(json.dumps({'passed':not errors,'errors':errors,**result},indent=2))
    return bool(errors)


if __name__=='__main__':
    raise SystemExit(main())
