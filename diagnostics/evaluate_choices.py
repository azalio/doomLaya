"""Measure real endpoint choices on a saved development dataset, without gameplay."""
import argparse,collections,hashlib,json,time
from pathlib import Path
import requests


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data',type=Path,required=True)
    parser.add_argument('--kind',nargs='+',default=['item'])
    parser.add_argument('--endpoint',default='http://127.0.0.1:8001/predict')
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    if args.output.exists():parser.error('output already exists')
    rows=[r for r in json.loads(args.data.read_text()) if r['kind'] in args.kind]
    if not rows:parser.error('no matching questions')
    session=requests.Session();session.trust_env=False
    counts=collections.defaultdict(lambda:dict(correct=0,total=0));results=[];weight_hash=None
    started=time.perf_counter()
    try:
        for row in rows:
            response=session.post(args.endpoint,json=dict(model='doom-adapted',state=row['state'],questions={row['kind']:row['question']}),timeout=30)
            response.raise_for_status();result=response.json();routing=result['routing']
            if weight_hash is None:weight_hash=routing['weights_sha256']
            if weight_hash!=routing['weights_sha256']:raise RuntimeError('Checkpoint changed during evaluation')
            answer=result['answers'][row['kind']];choice=answer['choice']
            if choice not in row['question']['criteria']:raise RuntimeError('Invalid model choice')
            correct=choice==row['label'];group=row['kind']+('/synthetic' if row.get('synthetic') else '/gameplay')
            counts[group]['correct']+=correct;counts[group]['total']+=1
            results.append(dict(kind=row['kind'],synthetic=row.get('synthetic',False),source_run=row.get('source_run'),source_tick=row.get('source_tick'),
                                expected=row['label'],choice=choice,correct=correct,answer=answer,question=row['question'],state=row['state']))
        summary=dict(note='Development validation; not a level-completion or generalization result',
                     routing=routing,data_sha256=hashlib.sha256(args.data.read_bytes()).hexdigest(),
                     seconds=round(time.perf_counter()-started,3),groups=dict(counts),results=results)
        args.output.write_text(json.dumps(summary,indent=2));print(json.dumps({k:v for k,v in summary.items() if k!='results'},indent=2))
    finally:session.close()

if __name__=='__main__':main()
