"""Probe explicit category then item choices, without changing game control."""
import argparse,copy,json,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from agent import LayaClient

DESCRIPTIONS={
    'Health':'Restore missing health with a reachable health pickup.',
    'Weapon':'Acquire a reachable gun that is not owned yet.',
    'Ammo':'Refill ammunition for an owned gun with a reachable pickup.',
    'Armor':'Increase low armor with a reachable armor pickup.',
    'Key':'Collect a reachable missing key for the route to the exit.',
    'Powerup':'Collect a reachable powerup.',
}

def main():
    p=argparse.ArgumentParser();p.add_argument('--endpoint',default='http://127.0.0.1:8001/predict');p.add_argument('--cases',type=Path,required=True);p.add_argument('--run',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.exists():p.error('output exists')
    cases=json.loads(a.cases.read_text())['results'];ticks={r['tick'] for r in cases};decisions={}
    for line in (a.run/'decisions.jsonl').open():
        d=json.loads(line)
        if d['tick'] in ticks:decisions[d['tick']]=d
    client=LayaClient(a.endpoint,'doom-adapted');routing=client.health();results=[]
    for case in cases:
        d=decisions[case['tick']];packet=d['packet'];targets=packet['targets']['item'];groups={}
        for oid,i in targets.items():groups.setdefault(i['category'],[]).append(oid)
        options={category:DESCRIPTIONS.get(category,category)+' Available: '+', '.join(targets[oid]['name']+' '+('reachable' if targets[oid].get('reachable') else 'unreachable') for oid in ids)+'.' for category,ids in groups.items()}
        question=dict(type='choice',instructions='Choose which kind of item is useful now. Consider health, armor, ammunition, owned weapons, keys, and path availability. Avoid unnecessary pickups.',criteria=options)
        first=client.predict(packet['state'],{'category':question});category=first['answers']['category']['choice']
        q=copy.deepcopy(packet['questions']['item']);q['criteria']={oid:value for oid,value in q['criteria'].items() if oid in groups[category]}
        second=client.predict(packet['state'],{'item':q});item=second['answers']['item']['choice']
        if any(r['routing']['weights_sha256']!=routing['weights_sha256'] for r in (first,second)):raise RuntimeError('Checkpoint changed')
        results.append(dict(tick=case['tick'],expected=case['expected'],expected_category=case['category'],category=category,item=item,answers=[first['answers'],second['answers']]))
    report=dict(note='Development input hierarchy probe only; no gameplay',routing=routing,cases=len(results),category_correct=sum(r['category']==r['expected_category'] for r in results),item_correct=sum(r['item']==r['expected'] for r in results),results=results)
    a.output.write_text(json.dumps(report,indent=2));print(json.dumps({k:v for k,v in report.items() if k not in ('routing','results')},indent=2))

if __name__=='__main__':main()
