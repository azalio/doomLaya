"""Balance previous command context while preserving offline action supervision."""
import argparse
import collections
import copy
import hashlib
import json
import random
import re
from pathlib import Path


def goal_headers(row):
    """Derive only available pickup and mechanism goals from the saved world."""
    options=row['question']['criteria'];state=row['state'];goals={}
    if 'continue' in options:raise ValueError('Explicit action questions are required')
    reachable=re.search(r'^Reachable items: (.*)$',state,re.M)
    reachable_ids=set(re.findall(r'\w+#([\w-]+)',reachable[1])) if reachable else set()
    if 'pickup' in options:
        items=re.search(r'^Items: (.*)$',state,re.M)
        if items:
            for name,oid,distance in re.findall(r'(\w+)#([\w-]+) \[\w+\] ([0-9.]+)m',items[1]):
                if oid in reachable_ids:goals.setdefault('pickup',[]).append(f'pickup #{oid} {name} {distance}m')
    if 'use_switch' in options:
        mechanisms=re.search(r'^Available mechanisms: (.*)$',state,re.M)
        if mechanisms:
            for entry in mechanisms[1].split('; '):
                match=re.match(r'(door switch|lift) #([\w-]+)(?: phase \w+)? ([0-9.]+)m',entry)
                if not match:continue
                kind,oid,distance=match.groups();name='Lift' if kind=='lift' else 'Door switch'
                goal=f'use_switch #{oid} {name} {distance}m'
                keys=re.search(r'Upper route keys: ([^.]+)',entry)
                if keys:goal+='; upper route keys: '+', '.join(re.findall(r'(\w+) \((?:missing|collected)\)',keys[1]))
                goals.setdefault('use_switch',[]).append(goal)
    return goals


def change_goal(row,goal):
    if row['kind']!='command':raise ValueError('Only root command supervision is supported')
    result=copy.deepcopy(row)
    lines=[line for line in row['state'].splitlines() if not line.startswith(('Current command:','Previous command result:'))]
    if goal:lines.insert(0,f'Current command: {goal}; status executing.')
    result['state']='\n'.join(lines)
    result.update(synthetic=True,source_type='counterfactual_root_previous_goal',
                  counterfactual_goal=goal or 'none')
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--replay',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if a.output.exists():p.error('output exists')
    manifest=dict(note='Offline label-preserving root command contrasts. Recorded stable54 and stable-fixed54 probes are not read. Original train/validation allocation retained. Only current command and previous execution feedback are changed; questions and world facts stay fixed. No runtime retention rule.',sources={},splits={})
    seen={};splits={}
    for split in ('train','validation'):
        path=a.replay/(split+'.json');original=json.loads(path.read_text())
        manifest['sources'][str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
        rng=random.Random(9251 if split=='train' else 9252);rows=[]
        for row in original:
            if row['kind']!='command':continue
            variants=[row,change_goal(row,None)]
            for candidates in goal_headers(row).values():variants.append(change_goal(row,rng.choice(candidates)))
            for value in variants:
                key=json.dumps([value['state'],value['question']],sort_keys=True)
                if key in seen:
                    if seen[key]!=value['label']:raise ValueError('Conflicting labels after goal augmentation')
                    continue
                seen[key]=value['label'];rows.append(value)
        rng.shuffle(rows);splits[split]=rows
        pairs=collections.Counter()
        for row in rows:
            goal=re.search(r'^Current command: (\w+)',row['state'],re.M)
            pairs[(goal[1] if goal else 'none')+' -> '+row['label']]+=1
        manifest['splits'][split]=dict(rows=len(rows),labels=dict(collections.Counter(r['label'] for r in rows)),previous_commands=dict(pairs))
    a.output.mkdir()
    for split,rows in splits.items():
        path=a.output/(split+'.json');path.write_text(json.dumps(rows,separators=(',',':')))
        manifest['splits'][split]['sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
    (a.output/'manifest.json').write_text(json.dumps(manifest,indent=2));print(json.dumps(manifest,indent=2))


if __name__=='__main__':main()
