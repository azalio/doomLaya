"""Replay a world while changing only the previous pickup or mechanism command."""
import argparse
import collections
import copy
import hashlib
import json
import re
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from agent import LayaClient


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('run',type=Path)
    p.add_argument('--start',type=float,required=True)
    p.add_argument('--end',type=float,required=True)
    p.add_argument('--episode',type=int,default=0)
    p.add_argument('--item',required=True)
    p.add_argument('--switch',required=True)
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--max-anti-goal',type=int)
    a=p.parse_args()
    if a.output.exists():p.error('output exists')
    if a.max_anti_goal is not None and a.max_anti_goal<0:p.error('max-anti-goal must be nonnegative')
    rows=[json.loads(x) for x in (a.run/'decisions.jsonl').read_text().splitlines()]
    rows=[r for r in rows if r['episode']==a.episode and a.start<=r['tick']/35<=a.end
          and a.item in r['packet']['targets'].get('item',{})
          and a.switch in r['packet']['targets'].get('switch',{})
          and {'pickup','use_switch'}<=set(r['packet']['questions']['command']['criteria'])]
    if len(rows)<12:raise ValueError('Need at least 12 matching recorded decisions')
    rows=[rows[i] for i in sorted({round(i*(len(rows)-1)/11) for i in range(12)})]
    client=LayaClient('http://127.0.0.1:8001/predict','doom-adapted');routing=client.health();records=[]
    try:
        for index,row in enumerate(rows):
            packet=copy.deepcopy(row['packet']);state=packet['state']
            states={'original':state,'no_goal':'\n'.join(l for l in state.splitlines() if not l.startswith('Current command:'))}
            for action,kind,oid in [('pickup','item',a.item),('use_switch','switch',a.switch)]:
                target=packet['targets'][kind][oid]
                goal=f"{action} #{oid} {target['name']} {target['distance']:.1f}m"
                if target.get('route_keys'):goal+='; upper route keys: '+', '.join(target['route_keys'])
                header=f"Current command: {goal}; status executing."
                states[action]=re.sub(r'^Current command:.*$',header,state,flags=re.M)
            results={};names=list(states);names=names[index%len(names):]+names[:index%len(names)]
            for name in names:
                result=client.predict(states[name],{'command':packet['questions']['command']})
                if result['routing']['weights_sha256']!=routing['weights_sha256']:raise RuntimeError('Checkpoint changed')
                results[name]=result['answers']['command']
            records.append(dict(tick=row['tick'],state=state,question=packet['questions']['command'],states=states,results=results))
            print(index+1,len(rows),{k:v['choice'] for k,v in results.items()},flush=True)
    finally:client.session.close()
    anti=sum(r['results']['pickup']['choice']=='use_switch' and r['results']['use_switch']['choice']=='pickup' for r in records)
    report=dict(note='Counterfactual command-goal diagnostic, not gameplay. Only the Current command line changes; all world facts and offered actions are fixed.',
                source_run=str(a.run),source_sha256={n:hashlib.sha256((a.run/n).read_bytes()).hexdigest() for n in ('config.json','decisions.jsonl')},
                routing=routing,cases=len(records),anti_goal_cases=anti,
                counts={n:dict(collections.Counter(r['results'][n]['choice'] for r in records)) for n in states},records=records)
    a.output.write_text(json.dumps(report,indent=2))
    print(json.dumps({k:v for k,v in report.items() if k not in ('records','routing')},indent=2))
    if a.max_anti_goal is not None and anti>a.max_anti_goal:raise SystemExit(f'FAIL: {anti} anti-goal cases, maximum {a.max_anti_goal}')


if __name__=='__main__':main()
