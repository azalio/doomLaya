"""Compare parallel and conditional questions using the same checkpoint and observations."""
import argparse,json,statistics,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from agent import LayaClient
from decision_questions import dependencies
from policy import decode
p=argparse.ArgumentParser();p.add_argument('--run',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--item-resource-facts',action='store_true');a=p.parse_args()
if a.output.exists():p.error('output exists')
client=LayaClient('http://127.0.0.1:8001/predict','doom-adapted')
routing=client.health()
rows=[json.loads(x) for x in (a.run/'decisions.jsonl').read_text().splitlines()]
records=[]
for index,row in enumerate(rows[::max(1,len(rows)//16)][:16]):
    packet=row['packet'];results={}
    if a.item_resource_facts:
        from resource_questions import with_resource_facts
        packet=with_resource_facts(packet)
    for schedule in (('parallel','conditional') if index%2 else ('conditional','parallel')):
        result=client.predict(packet['state'],packet['questions'],dependencies(packet) if schedule=='conditional' else None)
        if result['routing']['weights_sha256']!=routing['weights_sha256']:raise RuntimeError('Checkpoint changed')
        results[schedule]=dict(latency_ms=result['latency_ms'],tokens=result['tokens'],directive=decode(result,packet,0),routing=result['routing'])
    records.append(dict(tick=row['tick'],same=results['parallel']['directive']==results['conditional']['directive'],**results))
client.session.close()
report={'note':'Offline HTTP schedule comparison; no gameplay or real-time acceptance.', 'routing':routing,'item_resource_facts':a.item_resource_facts,'states':len(records),'same_decisions':sum(r['same'] for r in records),
        'p50_ms':{mode:statistics.median(r[mode]['latency_ms'] for r in records) for mode in ('parallel','conditional')},'records':records}
a.output.write_text(json.dumps(report,indent=2));print(json.dumps({k:v for k,v in report.items() if k!='records'},indent=2))
