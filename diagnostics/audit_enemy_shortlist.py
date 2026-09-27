"""Read-only audit of observed enemies omitted from the model's target choices."""
import argparse,collections,json
from pathlib import Path


def audit(run):
    decisions={d['tick']:d for d in map(json.loads,(run/'decisions.jsonl').open())};counts=collections.Counter();cases=[]
    for row in map(json.loads,(run/'telemetry.jsonl').open()):
        decision=decisions.get(row['tick'])
        if decision is None:continue
        targets=decision['packet']['targets'].get('enemy',{});visible=[e for e in row['enemies'] if e.get('visible',True)]
        omitted=[e for e in visible if str(e['id']) not in targets];current=(decision['packet'].get('enemy_commitment') or {}).get('target_id')
        counts['decisions']+=1;counts['visible_omitted_states']+=bool(omitted)
        previous_omitted=any(str(e['id'])==str(current) for e in omitted);counts['previous_visible_omitted']+=previous_omitted
        if omitted:cases.append(dict(tick=row['tick'],episode=row['episode'],latest_accepted_target=current,previous_visible_omitted=previous_omitted,selected_target=(decision['directive'].get('target') or {}).get('id'),omitted=[{k:e[k] for k in ('id','name','distance')} for e in omitted]))
    return dict(run=str(run),counts=dict(counts),cases=cases)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('run',type=Path);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.exists():p.error('Output exists')
    report=dict(note=__doc__+' Uses request-time recorded perception, not unknown world actors. This audit alone does not show that an omitted target caused death.',**audit(a.run));a.output.write_text(json.dumps(report,indent=2));print(report['counts'])
