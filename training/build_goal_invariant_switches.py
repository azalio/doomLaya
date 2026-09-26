"""Balance mechanism goal context and retain exact recorded command supervision."""
import argparse
import collections
import copy
import hashlib
import json
import random
import re
from pathlib import Path


def change_goal(row,goal):
    result=copy.deepcopy(row);description=row['question']['criteria'][goal]
    distance=re.search(r'Distance ([0-9.]+)m',description)
    if not distance:raise ValueError('Missing mechanism distance: '+description)
    name='Lift' if 'lift #' in description else 'Door switch' if 'door switch #' in description else 'Switch'
    header=f"Current command: use_switch #{goal} {name} {distance[1]}m; status executing."
    lines=[l for l in row['state'].splitlines() if not l.startswith(('Current command:','Previous command result:'))]
    result['state']=header+'\n'+'\n'.join(lines)
    result.update(synthetic=True,source_type='counterfactual_switch_previous_goal',original_source_type=row.get('source_type'),goal_variant='selected' if goal==row['label'] else 'alternative',counterfactual_goal=goal)
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--switches',type=Path,required=True)
    p.add_argument('--commands',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if a.output.exists():p.error('output exists')
    manifest=dict(note='Label-preserving mechanism-goal contrasts plus unchanged recorded command training. The fast54 switch-loop fixture is excluded from training. No runtime goal retention rule.',sources={},splits={})
    seen={};splits={}
    for split in ('train','validation'):
        rng=random.Random(2771 if split=='train' else 2772);pool=[]
        path=a.commands/(split+'.json');pool.extend(json.loads(path.read_text()));manifest['sources'][str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
        path=a.switches/(split+'.json');original=[r for r in json.loads(path.read_text()) if r['kind']=='switch'];manifest['sources'][str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
        for row in original:
            pool.extend([row,change_goal(row,row['label'])])
            alternatives=[oid for oid in row['question']['criteria'] if oid!=row['label']]
            if alternatives:pool.append(change_goal(row,rng.choice(alternatives)))
        rows=[]
        for row in pool:
            key=json.dumps([row['state'],row['question']],sort_keys=True)
            if key in seen:
                if seen[key]!=row['label']:raise ValueError('Conflicting labels')
                continue
            seen[key]=row['label'];rows.append(row)
        rng.shuffle(rows);splits[split]=rows
        offered=same=0
        for row in rows:
            if row['kind']!='switch':continue
            goal=re.search(r'Current command: use_switch #([^ ;]+)',row['state'])
            if goal and goal[1] in row['question']['criteria']:offered+=1;same+=row['label']==goal[1]
        manifest['splits'][split]=dict(rows=len(rows),kinds=dict(collections.Counter(r['kind'] for r in rows)),previous_goals=dict(offered=offered,selected=same))
    a.output.mkdir()
    for split,rows in splits.items():
        path=a.output/(split+'.json');path.write_text(json.dumps(rows,indent=2))
        manifest['splits'][split]['sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
    (a.output/'manifest.json').write_text(json.dumps(manifest,indent=2));print(json.dumps(manifest,indent=2))


if __name__=='__main__':main()
