"""Measure the two observed loop patterns on identical saved model inputs."""
import argparse,collections,copy,json,re,statistics,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from agent import LayaClient,JevClient
from policy import decode


def select(run):
    counts=collections.Counter();last={};cases=[]
    for line in (run/'decisions.jsonl').open():
        d=json.loads(line)
        if not d.get('applied'):continue
        packet=d['packet'];command=d['directive'];target=command.get('target') or {};case=None
        keys=re.search(r'Collected keys: ([^.]+)',d['state']);keys=keys.group(1).split(', ') if keys else []
        enemies=list(packet.get('targets',{}).get('enemy',{}).values())
        if command['action']=='use_switch' and target.get('kind')=='lift' and target.get('phase')=='call' and target.get('route_keys') and all(c in keys for c in target['route_keys']) and not enemies:case='collected_lift'
        if command['action']=='attack' and enemies and min(e['distance'] for e in enemies)>=30:case='distant_combat'
        if case is None or counts[case]>=20 or d['tick']-last.get(case,-10000)<35:continue
        counts[case]+=1;last[case]=d['tick'];cases.append(dict(case=case,tick=d['tick'],keys=keys,packet=packet,original=command,original_routing=d['routing']))
    return cases


def repeats(case,command):
    target=command.get('target') or {}
    if case['case']=='collected_lift':return command['action']=='use_switch' and target.get('kind')=='lift' and target.get('phase')=='call' and bool(target.get('route_keys')) and all(c in case['keys'] for c in target['route_keys'])
    return command['action']=='attack' and target.get('distance',0)>=30


def main():
    p=argparse.ArgumentParser();p.add_argument('run',type=Path);p.add_argument('--prepare-only',action='store_true');p.add_argument('--explicit',action='store_true');p.add_argument('--model',choices=['doom-adapted','jev'],default='doom-adapted');p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.exists():p.error('output exists')
    cases=select(a.run)
    if a.prepare_only:
        a.output.write_text(json.dumps(cases,indent=2));print(dict(collections.Counter(c['case'] for c in cases)));return
    client=JevClient() if a.model=='jev' else LayaClient('http://127.0.0.1:8001/predict','doom-adapted');routing=client.health();rows=[];served_model=None
    for c in cases:
        p=copy.deepcopy(c['packet'])
        if a.explicit:
            from diagnostics.probe_decision_context import explicit
            explicit(p)
        r=client.predict(p['state'],p['questions'],p.get('question_dependencies'));actual=decode(r,p,1)
        if a.model=='doom-adapted':
            if r['routing']['weights_sha256']!=routing['weights_sha256']:raise RuntimeError('Checkpoint changed')
        else:
            actual_model=r['routing']['served_model']
            if served_model is not None and actual_model!=served_model:raise RuntimeError('Served model changed')
            served_model=actual_model
        rows.append(dict(c,actual=actual,repeated=repeats(c,actual),answers=r['answers'],routing=r['routing'],latency_ms=r['latency_ms'],cost_usd=r.get('cost_usd',0)))
    summary={kind:dict(total=sum(r['case']==kind for r in rows),repeated=sum(r['case']==kind and r['repeated'] for r in rows),choices=dict(collections.Counter(r['actual']['action']+' '+str((r['actual'].get('target') or {}).get('id')) for r in rows if r['case']==kind))) for kind in {r['case'] for r in rows}}
    report=dict(note='Selected development loop states. Changing an answer is not proof of completing a level.',routing=routing,model=a.model,explicit_actions=a.explicit,cost_usd=sum(r['cost_usd'] for r in rows),latency_ms_median=statistics.median(r['latency_ms'] for r in rows),summary=summary,results=rows)
    a.output.write_text(json.dumps(report,indent=2));print(json.dumps({k:v for k,v in report.items() if k not in ('routing','results')},indent=2));client.session.close()

if __name__=='__main__':main()
