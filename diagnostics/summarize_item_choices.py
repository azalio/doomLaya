"""Separate exact-label agreement from observed facts about chosen items."""
import argparse
import collections
import hashlib
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from items import WEAPONS
from resource_questions import ammo_pool,has_pool_weapon


def summarize(probe,run):
    data=json.loads(probe.read_text())
    cases=json.loads(Path(data['challenge']).read_text())
    if hashlib.sha256(Path(data['challenge']).read_bytes()).hexdigest()!=data['challenge_sha256']:
        raise ValueError('Challenge changed since inference')
    decisions={d['tick']:d for d in map(json.loads,(run/'decisions.jsonl').open())}
    counts=collections.defaultdict(collections.Counter);details=[]
    for row in data['results']:
        if row['kind']!='item':continue
        case=cases[row['index']]
        if case['source_run']!=run.name:raise ValueError('Source run mismatch')
        packet=decisions[row['source_tick']]['packet'];observed=packet['observation']
        for variant,answer in row['answers'].items():
            item=packet['targets']['item'][answer['choice']];c=counts[variant]
            c['choices']+=1;c['exact_label_matches']+=answer['correct']
            reachable=item.get('reachable');c['unreachable']+=reachable is False
            c['reachability_unknown']+=reachable is None;c['category_'+item['category']]+=1
            facts=dict(reachable=reachable,health=observed['hp'],armor=observed['armor'])
            if item['name'] in ('Medikit','Stimpack'):
                c['standard_health_when_hp_ge100']+=observed['hp']>=100
                c['different_label_reachable_health_below100']+=not answer['correct'] and reachable is True and observed['hp']<100
            if item['category']=='Weapon' and item['name'] in WEAPONS:
                facts['weapon_owned']=bool(observed['inventory'][str(WEAPONS[item['name']])]['owned'])
                c['already_owned_weapon']+=facts['weapon_owned']
            if item['category']=='Ammo':
                pool,slot=ammo_pool(item['name']);facts['ammo_pool']=pool
                facts['ammo_count']=observed['inventory'][slot]['ammo']
                facts['compatible_weapon_owned']=has_pool_weapon(observed['inventory'],slot)
                c['ammo_without_compatible_weapon']+=not facts['compatible_weapon_owned']
            details.append(dict(variant=variant,tick=row['source_tick'],expected=row['expected'],choice=answer['choice'],name=item['name'],category=item['category'],distance=item['distance'],exact_match=answer['correct'],facts=facts))
    return dict(note='Frozen development choices, not gameplay. Facts are not a utility score: an owned weapon may supply ammo; ammo capacity and travel hazards are not evaluated.',probe=str(probe),probe_sha256=hashlib.sha256(probe.read_bytes()).hexdigest(),run=str(run),routing=data['routing'],counts={k:dict(v) for k,v in counts.items()},choices=details)


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('probe',type=Path);p.add_argument('--run',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.exists():p.error('output exists')
    report=summarize(a.probe,a.run);a.output.write_text(json.dumps(report,indent=2));print(json.dumps(report['counts'],indent=2))


if __name__=='__main__':main()
