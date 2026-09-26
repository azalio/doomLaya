"""Resource-grounded decisions with random candidate order and object identities."""
import argparse
import collections
import copy
import hashlib
import json
import random
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from training.correct_reachable_rollout import corrections
from training.resource_augmentation import resource_facts,shuffle_and_rename


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--replay',type=Path,required=True);p.add_argument('--run',type=Path,required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();a.output.mkdir(exist_ok=False)
    recent,_=corrections(a.run,2,True,True,True);heldout={1,4};seen=set()
    manifest=dict(note='Offline supervised learning; no teacher at runtime. Validation is development data used for checkpoint selection.',item_resource_facts=True,pickup_recent_targets=True,heldout_recent_episodes=sorted(heldout),sources={},splits={})
    for root,names in ((a.replay,('train.json','validation.json')),(a.run,('config.json','telemetry.jsonl','decisions.jsonl'))):
        for name in names:
            path=root/name;manifest['sources'][str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
    for split in ('train','validation'):
        rng=random.Random(19281 if split=='train' else 19282)
        pool=json.loads((a.replay/(split+'.json')).read_text());groups=collections.defaultdict(list)
        for row in recent:
            if (row['source_episode'] in heldout)==(split=='validation'):groups[row['kind']].append(row)
        for kind,values in groups.items():
            rng.shuffle(values);cap=dict(command=250,item=300,weapon=80,switch=120,movement=120,enemy=60,combat=160)[kind]
            if split=='validation':cap=max(20,cap//3)
            pool.extend(values[:cap])
        rows=[];augmented=0
        for original in pool:
            row=resource_facts(original);key=json.dumps([row['state'],row['question']],sort_keys=True)
            if key in seen:continue
            seen.add(key)
            if split=='train' and rng.random()<.75:row=shuffle_and_rename(row,rng);augmented+=1
            rows.append(row)
        rng.shuffle(rows);path=a.output/(split+'.json');path.write_text(json.dumps(rows,indent=2))
        manifest['splits'][split]=dict(rows=len(rows),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),augmented_rows=augmented,kinds=dict(collections.Counter(row['kind'] for row in rows)))
    (a.output/'manifest.json').write_text(json.dumps(manifest,indent=2));print(json.dumps(manifest['splits'],indent=2))


if __name__=='__main__':main()
