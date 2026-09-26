"""Dense command supervision from successful recorded MAP02 demonstrations."""
import argparse
import collections
import hashlib
import json
import random
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import vizdoom
from doomlib.mission import Mission,map_data
from training.build_committed_dataset import examples,demonstration_packets
from training.build_explicit_curriculum import normalize


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--train-demo',type=Path,required=True)
    p.add_argument('--validation-demo',type=Path,required=True)
    p.add_argument('--replay',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if a.output.exists():p.error('output exists')
    if a.train_demo.resolve()==a.validation_demo.resolve():p.error('demo split overlaps')
    mission=Mission(map_data(Path(vizdoom.__file__).parent/'freedoom2.wad','MAP02',3))
    routes={'728':['red'],'805':['blue']};seen={};splits={}
    manifest=dict(note='Offline teacher demonstrations only, at every recorded decision. Dense full contexts and balanced command replay. Held-out model death-window excluded. No runtime teacher.',sources={},splits={})
    for split,demo in [('train',a.train_demo),('validation',a.validation_demo)]:
        pool=[]
        for name in ('config.json','telemetry.jsonl','examples.json'):
            path=demo/name;manifest['sources'][str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
        for packet,gold,tick,episode in demonstration_packets(demo,mission):
            pool.extend(row for row in examples(packet,gold,demo.name,tick,episode,True,True) if row['kind']=='command')
        count_dense=len(pool);path=a.replay/(split+'.json')
        manifest['sources'][str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
        groups=collections.defaultdict(list)
        for row in json.loads(path.read_text()):
            if row['kind']=='command':groups[row['label']].append(row)
        rng=random.Random(11601 if split=='train' else 11602)
        for values in groups.values():
            rng.shuffle(values);pool.extend(values[:100 if split=='train' else 25])
        rows=[]
        for original in pool:
            row=normalize(original,routes);key=json.dumps([row['state'],row['question']],sort_keys=True)
            if key in seen:
                if seen[key]!=row['label']:raise ValueError('Conflicting command supervision')
                continue
            seen[key]=row['label'];rows.append(row)
        rng.shuffle(rows);splits[split]=rows
        manifest['splits'][split]=dict(rows=len(rows),dense_before_dedup=count_dense,labels=dict(collections.Counter(r['label'] for r in rows)),both_keys=sum('Collected keys: blue, red.' in r['state'] or 'Collected keys: red, blue.' in r['state'] for r in rows))
    a.output.mkdir()
    for split,rows in splits.items():
        path=a.output/(split+'.json');path.write_text(json.dumps(rows,indent=2))
        manifest['splits'][split]['sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
    (a.output/'manifest.json').write_text(json.dumps(manifest,indent=2))
    print(json.dumps(manifest,indent=2))


if __name__=='__main__':main()
