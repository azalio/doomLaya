"""Balance previous pickup goals without changing the item supervision target."""
import argparse
import collections
import copy
import hashlib
import json
import random
import re
from pathlib import Path


def change_goal(row,goal):
    result=copy.deepcopy(row)
    description=row['question']['criteria'][goal]
    name=description.split(';')[0].split(' (')[0]
    distance=re.search(r'([0-9.]+)m',description)
    if not distance:raise ValueError('Missing candidate distance: '+description)
    header=f"Current command: pickup #{goal} {name} {distance[1]}m; status executing."
    lines=[line for line in row['state'].splitlines() if not line.startswith(('Current command:','Previous command result:'))]
    result['state']=header+'\n'+'\n'.join(lines)
    result.update(synthetic=True,source_type='counterfactual_item_previous_goal',original_source_type=row.get('source_type'),goal_variant='selected' if goal==row['label'] else 'alternative',counterfactual_goal=goal)
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--replay',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.exists():p.error('output exists')
    splits={};seen=set();manifest=dict(note='Offline label-preserving item-goal augmentation. Original train/validation allocation retained. No teacher or extra decision rule at runtime.',sources={},splits={})
    for split in ('train','validation'):
        path=a.replay/(split+'.json');original=json.loads(path.read_text());rng=random.Random(3971 if split=='train' else 3972);rows=[]
        for row in original:
            variants=[row]
            if row['kind']=='item':
                variants.append(change_goal(row,row['label']))
                alternatives=[oid for oid,description in row['question']['criteria'].items() if oid!=row['label'] and 'unreachable' not in description]
                if alternatives:variants.append(change_goal(row,rng.choice(alternatives)))
            for value in variants:
                key=json.dumps([value['state'],value['question']],sort_keys=True)
                if key in seen:continue
                seen.add(key);rows.append(value)
        rng.shuffle(rows);splits[split]=rows
        manifest['sources'][str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
        counts=collections.Counter()
        for row in rows:
            if row['kind']!='item':continue
            match=re.search(r'Current command: pickup #([^ ;]+)',row['state'])
            if match and match[1] in row['question']['criteria']:
                counts['offered_previous_goal']+=1;counts['selected_previous_goal']+=match[1]==row['label']
        manifest['splits'][split]=dict(rows=len(rows),kinds=dict(collections.Counter(r['kind'] for r in rows)),previous_goals=dict(counts),source_types=dict(collections.Counter(r['source_type'] for r in rows)))
    a.output.mkdir()
    for split,rows in splits.items():
        path=a.output/(split+'.json');path.write_text(json.dumps(rows,indent=2));manifest['splits'][split]['sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
    (a.output/'manifest.json').write_text(json.dumps(manifest,indent=2));print(json.dumps(manifest,indent=2))


if __name__=='__main__':main()
