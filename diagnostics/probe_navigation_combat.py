"""Ask Laya for optional fire during recorded navigation decisions."""
import argparse
import collections
import copy
import hashlib
import json
import statistics
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from agent import LayaClient
from decision_questions import with_navigation_combat,dependencies,decode


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('run',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.exists():p.error('output exists')
    groups=collections.defaultdict(list)
    for line in (a.run/'decisions.jsonl').open():
        row=json.loads(line);action=row['directive']['action']
        if action in ('open_door','use_switch','exit','explore'):
            enemies=row['packet'].get('targets',{}).get('enemy',{})
            category=action+(' with enemy' if enemies else ' clear')
            if not groups[category] or row['tick']-groups[category][-1]['tick']>=175:groups[category].append(row)
    rows=[]
    for values in groups.values():
        indices=sorted({round(i*(len(values)-1)/5) for i in range(6)})
        rows.extend(values[i] for i in indices)
    client=LayaClient('http://127.0.0.1:8001/predict','doom-adapted');routing=client.health();records=[]
    for i,row in enumerate(rows):
        old=copy.deepcopy(row['packet']);new=with_navigation_combat(copy.deepcopy(old),include_recent=True)
        answers={}
        for name,packet in ([('original',old),('navigation',new)] if i%2 else [('navigation',new),('original',old)]):
            result=client.predict(packet['state'],packet['questions'],dependencies(packet))
            if result['routing']['weights_sha256']!=routing['weights_sha256']:raise RuntimeError('Checkpoint changed')
            answers[name]=dict(directive=decode(result,packet,0),answers=result['answers'],latency_ms=result['latency_ms'])
        previous,current=answers['original']['directive'],answers['navigation']['directive']
        target=current.get('combat_target')
        records.append(dict(tick=row['tick'],episode=row['episode'],same_primary=all(previous.get(k)==current.get(k) for k in ('action','target','weapon','movement')),combat_target=target,**answers))
        print(i+1,len(rows),current['action'],None if target is None else (target['id'],target.get('visible')),flush=True)
    client.session.close()
    result=dict(note='Offline model calls on frozen development states; no gameplay or completion claim.',source_run=str(a.run),source_sha256={name:hashlib.sha256((a.run/name).read_bytes()).hexdigest() for name in ('config.json','decisions.jsonl')},routing=routing,cases=len(records),same_primary=sum(r['same_primary'] for r in records),secondary_targets=sum(r['combat_target'] is not None for r in records),p50_ms={name:statistics.median(r[name]['latency_ms'] for r in records) for name in ('original','navigation')},records=records)
    a.output.write_text(json.dumps(result,indent=2));print(json.dumps({k:v for k,v in result.items() if k not in ('routing','records')},indent=2))


if __name__=='__main__':main()
