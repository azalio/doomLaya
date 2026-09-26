"""Replay held-out failure observations through the real model endpoint."""
import argparse,collections,copy,json,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import vizdoom
from agent import LayaClient
from mission import Mission,map_data
from policy import request,decode
from training.map2_teacher import labels


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('run',type=Path);p.add_argument('--endpoint',default='http://127.0.0.1:8001/predict');p.add_argument('--output',type=Path,required=True);p.add_argument('--per-case',type=int,default=3);p.add_argument('--episodes',nargs='+',type=int);a=p.parse_args()
    if a.output.exists():p.error('output already exists')
    states=[json.loads(line) for line in (a.run/'telemetry.jsonl').read_text().splitlines()]
    decisions=[json.loads(line) for line in (a.run/'decisions.jsonl').read_text().splitlines()]
    mission=Mission(map_data(Path(vizdoom.__file__).parent/'freedoom2.wad','MAP02',3))
    class Geometry:
        @staticmethod
        def nearest(point):return point
    selected=[];counts=collections.Counter();last={}
    for d in decisions:
        if d['tick']>=len(states):continue
        if a.episodes is not None:
            if d['episode'] not in a.episodes:continue
        elif d['tick']//1050%5!=4:continue
        s=copy.deepcopy(states[d['tick']]);packet=d['packet']
        if s.get('map')!='MAP02' or packet['observation'].get('reachable_items') is None:continue
        s['execution']=copy.deepcopy(packet['observation']['execution'])
        memory={item['id']:copy.deepcopy(item) for item in packet.get('targets',{}).get('item',{}).values()}
        reachable={(i['x'],i['y']) for i in memory.values() if i.get('reachable')}
        flat=request(s,memory,mission);gold=labels(flat,s,reachable,Geometry());expected=flat['commands'][gold['command']]
        old=d['directive'];expected_id=(expected.get('target') or {}).get('id');old_id=(old.get('target') or {}).get('id')
        if old['action']==expected['action'] and old_id==expected_id:continue
        case=old['action']+' -> '+expected['action']
        if counts[case]>=a.per_case or d['tick']-last.get(case,-10000)<175:continue
        counts[case]+=1;last[case]=d['tick'];selected.append((d,expected,flat['weapons'][gold['weapon']],case))
    client=LayaClient(a.endpoint,'doom-adapted');routing=client.health();results=[];started=time.perf_counter()
    try:
        for d,expected,weapon,case in selected:
            packet=d['packet'];result=client.predict(d['state'],packet['questions'],packet.get('question_dependencies'));actual=decode(result,packet,1)
            if result['routing']['weights_sha256']!=routing['weights_sha256']:raise RuntimeError('Checkpoint changed')
            key=lambda value:(value['action'],(value.get('target') or {}).get('id'))
            results.append(dict(case=case,tick=d['tick'],old=d['directive'],expected=dict(expected,weapon=weapon),actual=actual,
                                command_correct=key(actual)==key(expected),weapon_correct=actual['weapon']==weapon,
                                state=d['state'],answers=result['answers']))
        report=dict(note='Selected development observations; not independent gameplay proof',selected_episodes=a.episodes,routing=routing,
                    seconds=round(time.perf_counter()-started,3),cases=len(results),command_correct=sum(r['command_correct'] for r in results),
                    weapon_correct=sum(r['weapon_correct'] for r in results),results=results)
        a.output.write_text(json.dumps(report,indent=2));print(json.dumps({k:v for k,v in report.items() if k not in ('results','routing')},indent=2))
    finally:client.session.close()

if __name__=='__main__':main()
