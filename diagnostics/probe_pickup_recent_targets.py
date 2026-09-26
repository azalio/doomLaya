"""Replay pickup observations where the nearest known threat was outside view."""
import argparse
import copy
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from agent import LayaClient
from decision_questions import with_pickup_combat


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('run',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.exists():p.error('output exists')
    cases=[];last=-10000
    for line in (a.run/'decisions.jsonl').open():
        d=json.loads(line)
        if not d['applied'] or d['directive']['action']!='pickup':continue
        enemies=d['packet'].get('targets',{}).get('enemy',{})
        if not enemies:continue
        nearest=min(enemies,key=lambda k:enemies[k]['distance'])
        if enemies[nearest].get('visible',True) or enemies[nearest]['distance']>15 or d['tick']-last<35:continue
        cases.append((d,nearest));last=d['tick']
        if len(cases)>=40:break
    client=LayaClient('http://127.0.0.1:8001/predict','doom-adapted');routing=client.health();results=[]
    try:
        for d,nearest in cases:
            if d['routing']['weights_sha256']!=routing['weights_sha256']:raise RuntimeError('Recorded and current checkpoints differ')
            packet=with_pickup_combat(copy.deepcopy(d['packet']),include_recent=True)
            result=client.predict(packet['state'],{'combat':packet['questions']['combat']})
            if result['routing']['weights_sha256']!=routing['weights_sha256']:raise RuntimeError('Checkpoint changed')
            choice=result['answers']['combat']['choice'];target=packet['combat_targets'].get(choice)
            results.append(dict(tick=d['tick'],episode=d['episode'],hp=packet['observation']['hp'],nearest=nearest,nearest_distance=packet['combat_targets'][nearest]['distance'],old_choice=d['answers']['combat']['choice'],new_choice=choice,selected_nearest=choice==nearest,selected_recent=bool(target and not target.get('visible',True)),question=packet['questions']['combat'],answer=result['answers']['combat']))
    finally:client.session.close()
    report=dict(note='Offline menu-availability probe. Choosing a recent threat does not prove successful combat or level completion.',routing=routing,cases=len(results),selected_nearest=sum(r['selected_nearest'] for r in results),selected_recent=sum(r['selected_recent'] for r in results),hold=sum(r['new_choice']=='hold' for r in results),results=results)
    a.output.write_text(json.dumps(report,indent=2));print(json.dumps({k:v for k,v in report.items() if k not in ('results','routing')},indent=2))


if __name__=='__main__':main()
