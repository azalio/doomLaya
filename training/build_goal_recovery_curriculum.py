"""Counterfactual current goals on recorded successful training trajectories."""
import argparse,collections,copy,hashlib,json,random,re,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import vizdoom
from doomlib.mission import Mission,map_data
from doomlib.decision_questions import split_command
from training.build_committed_dataset import demonstration_packets,examples


def fingerprint(row):
    return json.dumps([row['state'],row['question']],sort_keys=True)


def build(paths,mission,rng,cap):
    groups=collections.defaultdict(list)
    for path in paths:
        for index,(packet,gold,tick,episode) in enumerate(demonstration_packets(path,mission)):
            if index%2:continue
            candidates=collections.defaultdict(list)
            for name,command in packet['commands'].items():
                if command['action'] in ('attack','pickup','use_switch','open_door','exit'):
                    candidates[command['action']].append(command)
            previous=[None]+[rng.choice(values) for values in candidates.values()]
            for old in previous:
                changed=copy.deepcopy(packet)
                execution=dict(packet['observation'].get('execution') or {})
                if old:
                    execution.update(action=old['action'],target_id=(old.get('target') or {}).get('id'),status='executing')
                else:execution.update(action='wait',target_id=None,status='waiting')
                execution['movement']=(old or {}).get('movement') if old and old['action']=='attack' else None
                changed['observation']['execution']=execution
                changed['state']='\n'.join(line for line in changed['state'].splitlines() if not line.startswith('Previous command result:'))
                changed['state']=re.sub(r'Current combat movement: [^.]+\.', 'Current combat movement: '+(execution['movement'] or 'stationary')+'.',changed['state'])
                for row in examples(changed,gold,path.name,tick,episode,True):
                    if row['kind']!='command':continue
                    row.update(synthetic=True,source_type='counterfactual_current_goal_on_recorded_world')
                    groups[(row['label'],row['category'])].append(row)
    result=[]
    for key,rows in groups.items():
        rng.shuffle(rows);result.extend(rows[:cap])
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--train',nargs='+',type=Path,required=True);p.add_argument('--validation',nargs='+',type=Path,required=True);p.add_argument('--replay',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if set(a.train)&set(a.validation):p.error('trajectory split overlaps')
    a.output.mkdir(exist_ok=False)
    mission=Mission(map_data(Path(vizdoom.__file__).parent/'freedoom2.wad','MAP02',3))
    manifest=dict(note='Synthetic current goals; recorded world and offline teacher targets remain unchanged. Development data, not independent gameplay evidence.',sources=[str(x) for x in a.train+a.validation],source_sha256={str(path/name):hashlib.sha256((path/name).read_bytes()).hexdigest() for path in a.train+a.validation for name in ('telemetry.jsonl','examples.json')},replay=str(a.replay),splits={})
    seen=set()
    for split,paths,cap in [('train',a.train,180),('validation',a.validation,45)]:
        rng=random.Random(3141 if split=='train' else 3142)
        rows=build(paths,mission,rng,cap)
        replay=json.loads((a.replay/(split+'.json')).read_text())
        for kind,limit in [('item',450),('switch',200),('movement',250),('weapon',200),('enemy',100)]:
            choices=[r for r in replay if r['kind']==kind];rng.shuffle(choices);rows.extend(choices[:limit if split=='train' else max(40,limit//3)])
        unique=[]
        for row in rows:
            key=fingerprint(row)
            if key not in seen:unique.append(row);seen.add(key)
        rng.shuffle(unique);path=a.output/(split+'.json');path.write_text(json.dumps(unique,indent=2))
        manifest['splits'][split]=dict(rows=len(unique),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),kinds=dict(collections.Counter(r['kind'] for r in unique)),commands=dict(collections.Counter(r['label'] for r in unique if r['kind']=='command')))
    (a.output/'manifest.json').write_text(json.dumps(manifest,indent=2));print(json.dumps(manifest,indent=2))


if __name__=='__main__':main()
