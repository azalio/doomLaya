"""Offline correction: a blocked pickup must open its door before collecting."""
import argparse,collections,copy,hashlib,json,random
from pathlib import Path


def correct(row):
    result=copy.deepcopy(row)
    if 'open_door' in row['question']['criteria'] and 'A closed door blocks movement; choose open_door to open it' in row['state']:
        result['label']='open_door';result['category']='blocked_door_prerequisite';result['source_type']='offline_door_prerequisite_correction'
    return result


def build(prefix,replay,output):
    if output.exists():raise ValueError('Output exists')
    pools={'train':[],'validation':[]}
    for row in map(json.loads,prefix.read_text().splitlines()):
        if row['kind']!='command':continue
        fixed=correct(row)
        if fixed['category']!='blocked_door_prerequisite':continue
        split='validation' if row.get('source_episode',0)%3==0 else 'train'
        pools[split].append(fixed)
    sources={str(prefix):hashlib.sha256(prefix.read_bytes()).hexdigest()};rng=random.Random(9305);seen={};splits={};result={}
    for split in ('train','validation'):
        path=replay/(split+'.json');sources[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
        new=pools[split];rng.shuffle(new)
        rows=[correct(r) for r in json.loads(path.read_text())]+new[:160 if split=='train' else 80]
        clean=[]
        for row in rows:
            key=json.dumps([row['state'],row['question']],sort_keys=True)
            if key in seen:
                if seen[key]!=row['label']:raise ValueError('Conflicting labels')
                continue
            seen[key]=row['label'];clean.append(row)
        rng.shuffle(clean);result[split]=clean
    output.mkdir()
    for split,rows in result.items():
        p=output/(split+'.json');p.write_text(json.dumps(rows,indent=2));splits[split]=dict(rows=len(rows),sha256=hashlib.sha256(p.read_bytes()).hexdigest(),categories=dict(collections.Counter(r['category'] for r in rows)))
    manifest=dict(note='Correct physical closed-door prerequisite on exact recorded command questions. The source prefix is immutable. MAP03 episode split; previous data retains allocation. No runtime rule. Development validation, not generalization.',sources=sources,splits=splits,builder_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest());(output/'manifest.json').write_text(json.dumps(manifest,indent=2));print(json.dumps(manifest,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('prefix',type=Path);p.add_argument('--replay',type=Path,default=Path('training/map3-route-recovery-v1'));p.add_argument('--output',type=Path,required=True);a=p.parse_args();build(a.prefix,a.replay,a.output)
