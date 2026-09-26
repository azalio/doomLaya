"""Freeze untrained explicit-game errors for before/after endpoint checks."""
import argparse
import collections
import copy
import json
import random
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import vizdoom
from mission import Mission,map_data
from policy import request
from decision_questions import split_command,TARGET_TYPES
from training.map2_teacher import labels


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('run',type=Path);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--include-correct',action='store_true');p.add_argument('--per-case',type=int,default=12);p.add_argument('--random-seed',type=int)
    a=p.parse_args()
    if a.output.exists():p.error('output exists')
    ds=[json.loads(line) for line in (a.run/'decisions.jsonl').open()]
    needed={d['tick'] for d in ds};states={}
    for line in (a.run/'telemetry.jsonl').open():
        s=json.loads(line)
        if s['tick'] in needed:states[s['tick']]=s
    mission=Mission(map_data(Path(vizdoom.__file__).parent/'freedoom2.wad','MAP02',3))
    class Geometry:
        @staticmethod
        def nearest(point):return point
    counts=collections.Counter();last={};rows=[]
    if a.random_seed is not None:random.Random(a.random_seed).shuffle(ds)
    for d in ds:
        if not d['applied'] or d['tick'] not in states:continue
        packet=d['packet'];s=copy.deepcopy(states[d['tick']]);s['execution']=packet['observation']['execution']
        memory={i['id']:i for i in packet.get('targets',{}).get('item',{}).values()}
        reachable={(i['x'],i['y']) for i in memory.values() if i.get('reachable')}
        flat=request(s,memory,mission);gold=labels(flat,s,reachable,Geometry())
        action,target,movement=split_command(gold['command'])
        expected={'command':action,'weapon':gold['weapon']}
        if action in TARGET_TYPES:expected[TARGET_TYPES[action]]=target
        if action=='attack':expected['movement']='continue' if movement==packet.get('current_movement') else movement
        visible=packet.get('combat_targets',{})
        if action=='pickup':expected['combat']=min(visible,key=lambda k:visible[k]['distance']) if visible else 'hold'
        for kind,label in expected.items():
            q=packet['questions'][kind]
            if label not in q['criteria']:raise ValueError((d['tick'],kind,label))
            answer=d['answers'][kind]['choice']
            if answer==label and not a.include_correct:continue
            case=kind
            if kind=='item':
                name=memory[next(i for i in memory if str(i)==label)]['category'];case+=':'+name
            if counts[case]>=a.per_case or abs(d['tick']-last.get(case,-10000))<175:continue
            counts[case]+=1;last[case]=d['tick']
            rows.append(dict(state=packet['state'],question=q,label=label,kind=kind,category=action,source_run=a.run.name,source_tick=d['tick'],source_episode=d['episode'],synthetic=False,source_type='development_decision_sample' if a.include_correct else 'heldout_development_mistake',baseline_choice=answer,baseline_routing=d['routing'],case=case))
    a.output.write_text(json.dumps(rows,indent=2));print(json.dumps(dict(rows=len(rows),cases=dict(counts),note='Development sample including correct answers; raw recorded requests preserved.' if a.include_correct else 'Selected failures, not an unbiased accuracy benchmark; raw recorded requests preserved.'),indent=2))


if __name__=='__main__':main()
