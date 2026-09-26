"""Hold a recorded world fixed and change only the previous item or mechanism goal."""
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
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('run',type=Path);p.add_argument('--kind',choices=['item','switch']);p.add_argument('--start',type=float,default=480);p.add_argument('--end',type=float,default=580);p.add_argument('--output',type=Path,required=True);p.add_argument('--max-anti-goal',type=int);a=p.parse_args()
    if a.output.exists():p.error('output exists')
    if a.max_anti_goal is not None and a.max_anti_goal<0:p.error('max-anti-goal must be nonnegative')
    if a.run.is_file():
        frozen=json.loads(a.run.read_text());goals=frozen['goals'];cases=frozen['cases'];kind=a.kind or frozen.get('kind','item')
        if frozen.get('kind',kind)!=kind:raise ValueError('Fixture kind mismatch')
        source=dict(source_run=frozen['source_run'],source_sha256=frozen['source_sha256'],fixture_sha256=hashlib.sha256(a.run.read_bytes()).hexdigest())
    else:
        kind=a.kind or 'item';action='pickup' if kind=='item' else 'use_switch'
        rows=[json.loads(x) for x in (a.run/'decisions.jsonl').open()];rows=[r for r in rows if a.start<=r['tick']/35<=a.end and r['directive']['action']==action]
        goals=[str(k) for k,_ in collections.Counter(r['directive']['target']['id'] for r in rows).most_common(2)]
        if len(goals)!=2:raise RuntimeError('Need a loop involving two targets')
        rows=[r for r in rows if set(goals)<=set(r['packet']['targets'].get(kind,{}))]
        cases=[rows[i] for i in sorted({round(i*(len(rows)-1)/11) for i in range(12)})]
        source=dict(source_run=str(a.run),source_sha256={n:hashlib.sha256((a.run/n).read_bytes()).hexdigest() for n in ('config.json','decisions.jsonl')})
    action='pickup' if kind=='item' else 'use_switch'
    client=LayaClient('http://127.0.0.1:8001/predict','doom-adapted');routing=client.health();records=[]
    for index,row in enumerate(cases):
        packet=row['packet'];states={'original':packet['state'],'no_goal':'\n'.join(l for l in packet['state'].splitlines() if not l.startswith('Current command:'))}
        for oid in goals:
            item=packet['targets'][kind][oid]
            text=f"Current command: {action} #{oid} {item['name']} {item['distance']:.1f}m; status executing."
            states['goal_'+oid]=re.sub(r'^Current command:.*$',text,packet['state'],flags=re.M)
        results={};names=list(states);names=names[index%len(names):]+names[:index%len(names)]
        for name in names:
            result=client.predict(states[name],{kind:packet['questions'][kind]})
            if result['routing']['weights_sha256']!=routing['weights_sha256']:raise RuntimeError('Checkpoint changed')
            results[name]=result['answers'][kind]
        records.append(dict(tick=row['tick'],hp=packet['observation']['hp'],goals={oid:packet['targets'][kind][oid] for oid in goals},results=results))
        print(index+1,len(cases),{k:v['choice'] for k,v in results.items()},flush=True)
    client.session.close()
    counts={name:dict(collections.Counter(r['results'][name]['choice'] for r in records)) for name in states}
    anti_goal=sum(r['results']['goal_'+goals[0]]['choice']==goals[1] and r['results']['goal_'+goals[1]]['choice']==goals[0] for r in records)
    report=dict(note='Counterfactual development diagnostic, not gameplay. Position, candidates and resources stay identical; only previous-goal text changes.',**source,kind=kind,routing=routing,goals=goals,cases=len(cases),anti_goal_cases=anti_goal,counts=counts,records=records)
    a.output.write_text(json.dumps(report,indent=2));print(json.dumps({k:v for k,v in report.items() if k not in ('records','routing')},indent=2))
    if a.max_anti_goal is not None and anti_goal>a.max_anti_goal:
        raise SystemExit(f'FAIL: {anti_goal} anti-goal cases, maximum {a.max_anti_goal}')


if __name__=='__main__':main()
