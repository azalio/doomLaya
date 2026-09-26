"""Offline DAgger labels from factual observations in a real model rollout."""
import argparse,collections,copy,hashlib,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import vizdoom
from mission import Mission,map_data
from policy import request
from training.map2_teacher import labels
from training.build_committed_dataset import examples
from decision_questions import split_command


def corrections(run,stride=2,explicit_actions=False,pickup_combat=False,pickup_recent=False,weapon_resupply=False):
    states={}
    decisions=[json.loads(line) for line in (run/'decisions.jsonl').read_text().splitlines()]
    needed={d['tick'] for d in decisions[::stride]}
    for line in (run/'telemetry.jsonl').read_text().splitlines():
        s=json.loads(line)
        if s['tick'] in needed:states[s['tick']]=s
    mission=Mission(map_data(Path(vizdoom.__file__).parent/'freedoom2.wad','MAP02',3))
    class Geometry:
        @staticmethod
        def nearest(point):return point
    counts=collections.Counter();rows=[]
    for d in decisions[::stride]:
        if d['tick'] not in states:continue
        s=copy.deepcopy(states[d['tick']]);packet=d['packet']
        if s.get('map')!='MAP02' or packet['observation'].get('reachable_items') is None:continue
        s['execution']=copy.deepcopy(packet['observation']['execution'])
        memory={item['id']:copy.deepcopy(item) for item in packet.get('targets',{}).get('item',{}).values()}
        reachable={(i['x'],i['y']) for i in memory.values() if i.get('reachable')}
        flat=request(s,memory,mission);gold=labels(flat,s,reachable,Geometry(),weapon_resupply=weapon_resupply)
        expected=split_command(gold['command'])[0];actual=d['directive']['action']
        counts[actual+' -> '+expected]+=1
        for row in examples(flat,gold,run.name,d['tick'],d['episode'],True,explicit_actions,pickup_combat,pickup_recent):
            row['source_type']='offline_correction_of_model_rollout';rows.append(row)
    return rows,counts


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('run',type=Path);p.add_argument('--output',type=Path,required=True);p.add_argument('--stride',type=int,default=2);p.add_argument('--explicit-actions',action='store_true');p.add_argument('--combat-during-pickup',action='store_true');p.add_argument('--weapon-resupply',action='store_true');a=p.parse_args()
    a.output.mkdir(exist_ok=False);rows,counts=corrections(a.run,a.stride,a.explicit_actions,a.combat_during_pickup,weapon_resupply=a.weapon_resupply)
    (a.output/'examples.json').write_text(json.dumps(rows,indent=2))
    manifest=dict(note='Offline labels only; the teacher is never used by the game agent',explicit_actions=a.explicit_actions,combat_during_pickup=a.combat_during_pickup,rows=len(rows),action_pairs=dict(counts),
                  source_sha256={name:hashlib.sha256((a.run/name).read_bytes()).hexdigest() for name in ('config.json','telemetry.jsonl','decisions.jsonl')})
    if a.weapon_resupply:manifest['weapon_resupply']=True
    (a.output/'manifest.json').write_text(json.dumps(manifest,indent=2));print(json.dumps(manifest,indent=2))

if __name__=='__main__':main()
