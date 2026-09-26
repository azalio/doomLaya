"""Audit shotgun upgrades from inventory, independent of model weapon choices."""
import argparse
import json
from pathlib import Path


def analyze(rows):
    equipped_delay=choice_delay=max_equipped=max_choice=0
    previous_episode=None;worst=None
    for s in rows:
        if s['episode']!=previous_episode:equipped_delay=choice_delay=0
        previous_episode=s['episode']
        inventory=s['inventory'];current=s['weapon']
        def loaded(slot,cost):
            entry=inventory.get(str(slot),{})
            return entry.get('owned',False) and entry.get('ammo',0)>=cost
        upgrade=(8 if loaded(8,2) and current in (1,2,3,9)
                 else 3 if loaded(3,1) and current in (1,2,9) else None)
        if upgrade and s['hp']>0:
            equipped_delay+=1
            selected=s.get('execution',{}).get('weapon')
            accepted=(selected==upgrade or (upgrade==3 and selected in (4,5,6,7,8)
                                           and loaded(selected,{4:1,5:1,6:1,7:40,8:2}[selected])))
            choice_delay=0 if accepted else choice_delay+1
        else:equipped_delay=choice_delay=0
        if equipped_delay>max_equipped:
            max_equipped=equipped_delay
            worst=dict(tick=s['tick'],seconds=s['seconds'],episode=s['episode'],equipped=current,available_upgrade=upgrade,model_selected=s.get('execution',{}).get('weapon'))
        max_choice=max(max_choice,choice_delay)
    return dict(scope='Loaded shotgun over pistol/melee; loaded super shotgun over ordinary shotgun/pistol/melee. Engine equip delay includes inference and weapon animation.',
                max_upgrade_delay_seconds=round(max_equipped/35,3),
                max_model_upgrade_choice_delay_seconds=round(max_choice/35,3),worst_upgrade_delay=worst)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('run',type=Path);a=p.parse_args()
    rows=[json.loads(line) for line in (a.run/'telemetry.jsonl').open()]
    result=analyze(rows);result['passed']=result['max_upgrade_delay_seconds']<=1.5
    (a.run/'weapon-verification.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2));raise SystemExit(not result['passed'])


if __name__=='__main__':main()
