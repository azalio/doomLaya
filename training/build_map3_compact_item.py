"""Project item examples and add offline resource labels from completed Laya runs."""
import argparse,collections,copy,hashlib,json,random
from pathlib import Path
from doomlib.compact_item import FORMAT,compact_item_input
from training.build_map3_resources import labels


def recorded(run):
    for decision in map(json.loads,(run/'decisions.jsonl').open()):
        packet=decision['packet']
        for kind,label,category in labels(packet):
            if kind=='item':
                yield dict(kind=kind,label=label,category='recorded_'+category,state=packet['state'],question=copy.deepcopy(packet['questions'][kind]),source_run=run.name,source_tick=decision['tick'],source_episode=decision['episode'],source_type='offline_resource_labels',synthetic=False)


def build(data,train_runs,heldout_runs,output):
    if output.exists():raise ValueError('Output exists')
    if set(map(Path.resolve,train_runs))&set(map(Path.resolve,heldout_runs)):raise ValueError('A run occurs in both splits')
    sources={};result={};seen={};removed=collections.Counter();rng=random.Random(9381)
    for split,runs in [('train',train_runs),('validation',heldout_runs)]:
        rows=[]
        for run in runs:
            path=run/'decisions.jsonl';sources[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
            groups=collections.defaultdict(list)
            for row in recorded(run):groups[row['category']].append(row)
            for group in groups.values():
                rng.shuffle(group);rows.extend(group[:250] if split=='train' else group)
        path=data/(split+'.json');sources[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest();rows+=json.loads(path.read_text());result[split]=[]
        for original in rows:
            if original['kind']!='item':raise ValueError('Expected only item examples')
            row=copy.deepcopy(original);row['raw_state']=row.get('raw_state',row['state'])
            row['state'],row['question']=compact_item_input(row['raw_state'],row['question'])
            if row['label'] not in row['question']['criteria']:raise ValueError('Unavailable label')
            key=json.dumps([row['state'],row['question']],sort_keys=True)
            if key in seen:
                removed[split+('_conflict' if seen[key]!=row['label'] else '_duplicate')]+=1;continue
            seen[key]=row['label'];result[split].append(row)
    output.mkdir();manifest=dict(input_projection=FORMAT,note='Observed health, armor, inventory, keys, reachability; original item choices. New labels use the existing offline resource teacher. Training and held-out runs are disjoint. Previous source split allocations retained. New rows take precedence over conflicting old examples within each split; train/validation duplicates removed train-first and counted. Same-map development, not independent generalization or gameplay proof.',sources=sources,train_runs=list(map(str,train_runs)),heldout_runs=list(map(str,heldout_runs)),removed=dict(removed),splits={},builder_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),projection_sha256=hashlib.sha256(Path('doomlib/compact_item.py').read_bytes()).hexdigest())
    for split,rows in result.items():
        p=output/(split+'.json');p.write_text(json.dumps(rows,indent=2));manifest['splits'][split]=dict(rows=len(rows),sha256=hashlib.sha256(p.read_bytes()).hexdigest(),categories=dict(collections.Counter(r['category'] for r in rows)))
    (output/'manifest.json').write_text(json.dumps(manifest,indent=2));print(json.dumps(manifest,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--data',type=Path,required=True);p.add_argument('--train-run',type=Path,action='append',default=[]);p.add_argument('--heldout-run',type=Path,action='append',default=[]);p.add_argument('--output',type=Path,required=True);a=p.parse_args();build(a.data,a.train_run,a.heldout_run,a.output)
