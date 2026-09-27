"""Validate movement choices and selected clearance on saved, offline examples."""
import argparse,collections,hashlib,json,re,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from agent import LayaClient


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('data',type=Path);p.add_argument('--raw-data',type=Path,help='Original movement rows when the server applies compact projection');p.add_argument('--endpoint',default='http://127.0.0.1:8002/predict');p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.exists():p.error('Output exists')
    client=LayaClient(a.endpoint,'doom-adapted')
    for i in range(60):
        try:health=client.health();break
        except Exception:
            if i==59:raise
            time.sleep(1)
    rows=json.loads(a.data.read_text());raw_lookup={}
    if a.raw_data:
        from doomlib.compact_movement import compact_movement_input
        for raw in json.loads(a.raw_data.read_text()):
            try:projected=compact_movement_input(raw['state'],raw['question'])
            except ValueError:continue  # Raw input may contain legacy replay excluded from the projected dataset.
            raw_lookup[json.dumps(projected,sort_keys=True)]=raw
    counts=collections.defaultdict(lambda:dict(correct=0,total=0));cases=[];blocked=0;measured=0
    for i,row in enumerate(rows):
        if row['kind']!='movement':raise ValueError('Expected movement examples only')
        raw=raw_lookup[json.dumps((row['state'],row['question']),sort_keys=True)] if a.raw_data else row
        answer=client.predict(raw['state'],{'movement':raw['question']});assert answer['routing']['weights_sha256']==health['weights_sha256'];choice=answer['answers']['movement']['choice'];correct=choice==row['label'];c=counts[row['category']];c['correct']+=correct;c['total']+=1
        match=re.search(r'Body clearance in this direction: ([0-9.]+)m',row['question']['criteria'][choice]);clearance=float(match[1]) if match else None
        if clearance is not None:measured+=1;blocked+=clearance<1
        cases.append(dict(index=i,expected=row['label'],choice=choice,selected_clearance=clearance))
        if i%100==0:print(i,len(rows),flush=True)
    report=dict(note='API accuracy on offline labels; clearance is measured input, not a guarantee of survival.',data=str(a.data),raw_data=str(a.raw_data) if a.raw_data else None,raw_data_sha256=hashlib.sha256(a.raw_data.read_bytes()).hexdigest() if a.raw_data else None,data_sha256=hashlib.sha256(a.data.read_bytes()).hexdigest(),routing=health,categories=dict(counts),correct=sum(c['correct'] for c in counts.values()),total=len(rows),selected_clearance_under_one_meter=blocked,measured_moving_choices=measured,cases=cases)
    a.output.write_text(json.dumps(report,indent=2));print({k:v for k,v in report.items() if k not in ('routing','cases')})

if __name__=='__main__':main()
