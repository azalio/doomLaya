"""Read-only audit: did the request omit known, reachable non-bonus health or armor?"""
import argparse,json,math
from pathlib import Path


def audit(run):
    decisions=iter(map(json.loads,(run/'decisions.jsonl').open()));decision=next(decisions,None)
    known={};episode=None;checked=0;cases=[];with_supplies=0
    for row in map(json.loads,(run/'telemetry.jsonl').open()):
        if episode!=row['episode']:known={};episode=row['episode']
        known.update({str(item['id']):item for item in row.get('items',())})
        while decision is not None and decision['tick']<=row['tick']:
            if decision['tick']!=row['tick']:raise ValueError('Decision tick not found in telemetry')
            packet=decision['packet'];obs=packet['observation'];reachable=obs.get('reachable_items') or {};offered=set(packet.get('targets',{}).get('item',{}));failures=set(row.get('target_failures',{}));resources=[]
            for key,available in reachable.items():
                item=known.get(key)
                if not available or key in failures or item is None or 'Bonus' in item['name']:continue
                useful=(item['category']=='Health' and obs['hp']<85) or (item['category']=='Armor' and obs['armor']<60)
                if useful:resources.append(dict(id=key,name=item['name'],distance=round(math.hypot(item['x']-row['x'],item['y']-row['y'])/32,2),offered=key in offered))
            checked+=1;with_supplies+=bool(resources)
            omitted=[item for item in resources if not item['offered']]
            if omitted:cases.append(dict(tick=row['tick'],episode=episode,hp=obs['hp'],armor=obs['armor'],action=decision['directive']['action'],offered_count=len(offered),omitted=omitted))
            decision=next(decisions,None)
        if decision is None:break
    return dict(run=str(run),decisions_checked=checked,states_with_known_reachable_useful_supplies=with_supplies,omission_states=len(cases),cases=cases)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('runs',nargs='+',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.exists():p.error('Output exists')
    results=[audit(run) for run in a.runs];a.output.write_text(json.dumps(dict(note=__doc__+' Useful here means HP below 85 or armor below 60. Failed targets are excluded. This does not evaluate unknown or unreachable supplies.',results=results),indent=2));print(json.dumps([{k:v for k,v in result.items() if k!='cases'} for result in results],indent=2))
