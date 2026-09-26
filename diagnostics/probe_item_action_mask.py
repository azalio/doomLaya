"""Check real model choices after removing only physically impossible items."""
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
from decision_questions import mask_unreachable_items,dependencies,decode


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('run',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.exists():p.error('output exists')
    groups=collections.defaultdict(list)
    for line in (a.run/'decisions.jsonl').open():
        row=json.loads(line);items=list(row['packet'].get('targets',{}).get('item',{}).values())
        if not items or all(i.get('reachable') for i in items):continue
        category='mixed' if any(i.get('reachable') for i in items) else 'none_reachable'
        if not groups[category] or row['tick']-groups[category][-1]['tick']>=26:groups[category].append(row)
    cases=[]
    for category,values in groups.items():
        cases.extend((category,values[i]) for i in sorted({round(i*(len(values)-1)/9) for i in range(10)}))
    client=LayaClient('http://127.0.0.1:8001/predict','doom-adapted');routing=client.health();records=[]
    for index,(category,row) in enumerate(cases):
        answers={};original=copy.deepcopy(row['packet']);masked=mask_unreachable_items(copy.deepcopy(original))
        for name,packet in ([('original',original),('masked',masked)] if index%2 else [('masked',masked),('original',original)]):
            result=client.predict(packet['state'],packet['questions'],dependencies(packet))
            if result['routing']['weights_sha256']!=routing['weights_sha256']:raise RuntimeError('Checkpoint changed')
            command=decode(result,packet,0)
            if name=='masked' and command['action']=='pickup' and command['target']['reachable'] is not True:raise RuntimeError('Impossible selected target')
            answers[name]=dict(directive=command,answers=result['answers'],latency_ms=result['latency_ms'])
        records.append(dict(category=category,tick=row['tick'],masked_items=len(masked['masked_unreachable_items']),**answers))
        print(index+1,len(cases),category,answers['original']['directive']['action'],'->',answers['masked']['directive']['action'],flush=True)
    client.session.close()
    counts={category:dict(cases=sum(r['category']==category for r in records),actions=dict(collections.Counter(r['masked']['directive']['action'] for r in records if r['category']==category))) for category in groups}
    result=dict(note='Frozen development observations. Physics limits available commands; all remaining choices come from Laya. No gameplay claim.',source_run=str(a.run),source_sha256={name:hashlib.sha256((a.run/name).read_bytes()).hexdigest() for name in ('config.json','decisions.jsonl')},routing=routing,cases=len(records),groups=counts,p50_ms={name:statistics.median(r[name]['latency_ms'] for r in records) for name in ('original','masked')},records=records)
    a.output.write_text(json.dumps(result,indent=2));print(json.dumps({k:v for k,v in result.items() if k not in ('routing','records')},indent=2))


if __name__=='__main__':main()
