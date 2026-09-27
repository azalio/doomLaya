"""Compare item or weapon head answers with offline labels on saved raw observations."""
import argparse,collections,hashlib,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from agent import LayaClient


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('data',type=Path);p.add_argument('--kind',choices=['weapon','item'],default='weapon');p.add_argument('--endpoint',default='http://127.0.0.1:8002/predict');p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.exists():p.error('Output exists')
    rows=json.loads(a.data.read_text());client=LayaClient(a.endpoint,'doom-adapted');health=client.health();counts=collections.defaultdict(lambda:dict(correct=0,total=0));cases=[]
    for i,row in enumerate(rows):
        if row['kind']!=a.kind:raise ValueError('Unexpected question kind')
        response=client.predict(row.get('raw_state',row['state']),{a.kind:row.get('raw_question',row['question'])})
        if response['routing']['weights_sha256']!=health['weights_sha256']:raise RuntimeError('Weights changed during probe')
        answer=response['answers'][a.kind];choice=answer['choice'];c=counts[row['category']];c['total']+=1;c['correct']+=choice==row['label']
        cases.append(dict(index=i,source_tick=row.get('source_tick'),category=row['category'],expected=row['label'],choice=choice,answer=answer))
        if i%100==0:print(i,len(rows),flush=True)
    report=dict(note='API agreement with offline resource labels; not gameplay success.',data=str(a.data),data_sha256=hashlib.sha256(a.data.read_bytes()).hexdigest(),routing=health,categories=dict(counts),correct=sum(c['correct'] for c in counts.values()),total=len(rows),cases=cases)
    a.output.write_text(json.dumps(report,indent=2));print({k:v for k,v in report.items() if k not in ('routing','cases')})


if __name__=='__main__':main()
