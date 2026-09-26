"""Dense explicit targets, pickup combat, and factual resource counterfactuals."""
import argparse
import collections
import copy
import hashlib
import json
import random
import re
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import vizdoom
from doomlib.mission import Mission,map_data
from doomlib.policy import request
from training.build_committed_dataset import examples,demonstration_packets
from training.correct_reachable_rollout import corrections
from training.map2_teacher import labels


class ObservedReachability:
    @staticmethod
    def nearest(point):return point


def resource_pairs(run,mission):
    decisions=[json.loads(line) for line in (run/'decisions.jsonl').read_text().splitlines()][::8]
    needed={d['tick'] for d in decisions};states={}
    for line in (run/'telemetry.jsonl').open():
        s=json.loads(line)
        if s['tick'] in needed:states[s['tick']]=s
    for d in decisions:
        if d['tick'] not in states:continue
        original=states[d['tick']]
        if original['map']!='MAP02':continue
        memory={i['id']:copy.deepcopy(i) for i in d['packet'].get('targets',{}).get('item',{}).values()}
        if not memory:continue
        reachable={(i['x'],i['y']) for i in memory.values() if i.get('reachable')}
        for variant in ('critical_health','full_health','empty_shells','loaded_shells'):
            s=copy.deepcopy(original);s['execution']=copy.deepcopy(d['packet']['observation']['execution'])
            if variant.endswith('health'):s['hp']=8 if variant=='critical_health' else 100
            else:
                if not any(s['inventory'][str(k)]['owned'] for k in (3,8)):continue
                for k in (3,8):s['inventory'][str(k)]['ammo']=0 if variant=='empty_shells' else 40
            packet=request(s,memory,mission);gold=labels(packet,s,reachable,ObservedReachability())
            for row in examples(packet,gold,run.name,d['tick'],d['episode'],True,True,True):
                if row['kind'] not in ('command','item','weapon'):continue
                row.update(synthetic=True,source_type='counterfactual_resource_state',pair_variant=variant)
                yield row


def normalize(row,routes):
    row=copy.deepcopy(row)
    if row['kind']=='command':
        row['question']['criteria'].pop('continue',None)
        if row['label']=='continue':row['label']=row['category']
    state=row['state'];keys=re.search(r'Collected keys: ([^.]+)',state)
    keys=keys.group(1).split(', ') if keys else []
    for oid,colors in routes.items():
        fact=' Upper route keys: '+', '.join(c+(' (collected)' if c in keys else ' (missing)') for c in colors)+'.'
        state=re.sub(r'(lift #'+oid+r' phase \w+ [0-9.]+m)(?! Upper route keys:)',lambda m:m[1]+fact,state)
        if row['kind']=='switch' and oid in row['question']['criteria'] and 'Upper route keys:' not in row['question']['criteria'][oid]:row['question']['criteria'][oid]+=fact
    row['state']=state
    assert row['label'] in row['question']['criteria']
    return row


def group(row):
    kind=row['kind']
    if kind=='command':return kind,row['label']
    if kind=='combat':return kind,'hold' if row['label']=='hold' else 'fire'
    if kind=='item':
        name=row['question']['criteria'][row['label']].split(';')[0].split(' ')[0]
        category=('health' if name in ('Medikit','Stimpack','HealthBonus') else 'armor' if 'Armor' in name else 'key' if 'Card' in name or 'Skull' in name else 'weapon' if name in ('Shotgun','SuperShotgun','Chaingun') else 'ammo')
        return kind,category
    return kind,'all'


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--run',type=Path,required=True)
    p.add_argument('--replay',type=Path,required=True)
    p.add_argument('--train-demo',type=Path,required=True)
    p.add_argument('--validation-demo',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if a.train_demo==a.validation_demo:p.error('demonstrations must differ')
    a.output.mkdir(exist_ok=False)
    mission=Mission(map_data(Path(vizdoom.__file__).parent/'freedoom2.wad','MAP02',3))
    routes={}
    for line in (a.run/'telemetry.jsonl').open():
        s=json.loads(line);routes.update({str(v['id']):v['route_keys'] for v in s['switches'] if v.get('route_keys')})
        if routes:break
    recent,_=corrections(a.run,2,True,True)
    recent+=list(resource_pairs(a.run,mission))
    heldout={1,4,7};seen=set()
    manifest=dict(note='Offline supervision only. Development validation selects checkpoints, not independent gameplay proof.',explicit_actions=True,combat_during_pickup=True,heldout_recent_episodes=sorted(heldout),routes=routes,sources={},splits={})
    for root,names in [(a.run,('config.json','telemetry.jsonl','decisions.jsonl')),(a.train_demo,('config.json','telemetry.jsonl','examples.json')),(a.validation_demo,('config.json','telemetry.jsonl','examples.json')),(a.replay,('train.json','validation.json'))]:
        for name in names:
            path=root/name;manifest['sources'][str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
    for split,demo in [('train',a.train_demo),('validation',a.validation_demo)]:
        rng=random.Random(7291 if split=='train' else 7292)
        pool=json.loads((a.replay/(split+'.json')).read_text())
        pool.extend(r for r in recent if (r['source_episode'] in heldout)==(split=='validation'))
        for packet,gold,tick,episode in demonstration_packets(demo,mission):
            if tick%72:continue
            pool.extend(examples(packet,gold,demo.name,tick,episode,True,True,True))
        groups=collections.defaultdict(list)
        for original in pool:
            row=normalize(original,routes);key=json.dumps([row['state'],row['question']],sort_keys=True)
            if key in seen:continue
            seen.add(key);groups[group(row)].append(row)
        rows=[]
        for (kind,category),values in groups.items():
            cap=dict(command=320,item=380,weapon=400,movement=350,switch=380,enemy=150,combat=200)[kind]
            if split=='validation':cap=max(30,cap//4)
            rng.shuffle(values);rows.extend(values[:cap])
        if split=='train':
            for row in rows:
                if rng.random()<.5:
                    options=list(row['question']['criteria'].items());rng.shuffle(options)
                    row['question']['criteria']=dict(options);row['option_order_augmented']=True
        rng.shuffle(rows);path=a.output/(split+'.json');path.write_text(json.dumps(rows,indent=2))
        manifest['splits'][split]=dict(rows=len(rows),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),kinds=dict(collections.Counter(r['kind'] for r in rows)),groups={kind+':'+category:sum(group(r)==(kind,category) for r in rows) for kind,category in groups},source_types=dict(collections.Counter(r['source_type'] for r in rows)))
    (a.output/'manifest.json').write_text(json.dumps(manifest,indent=2));print(json.dumps(manifest['splits'],indent=2))


if __name__=='__main__':main()
