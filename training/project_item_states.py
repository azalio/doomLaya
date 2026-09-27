"""Prepare supervision matching explicit per-question goal-free model inputs."""
import argparse,collections,copy,hashlib,json
from pathlib import Path


def build(data,output,kind='item'):
    if output.exists():raise ValueError('Output exists')
    seen={};splits={};source_hashes={};removed=collections.Counter();result={}
    for split in ('train','validation'):
        path=data/(split+'.json');source_hashes[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest();rows=[]
        for source in json.loads(path.read_text()):
            if source['kind']!=kind:raise ValueError('Unexpected question kind')
            row=copy.deepcopy(source)
            row['state']='\n'.join(line for line in row['state'].splitlines() if not line.startswith('Current command:'))
            key=json.dumps([row['state'],row['question']],sort_keys=True)
            if key in seen:
                if seen[key]!=row['label']:raise ValueError('Conflicting labels after previous-goal removal')
                removed[split]+=1;continue
            seen[key]=row['label'];row['input_projection']='without-current-command-v1';rows.append(row)
        result[split]=rows
    output.mkdir(parents=True)
    for split,rows in result.items():
        path=output/(split+'.json');path.write_text(json.dumps(rows,indent=2));splits[split]=dict(rows=len(rows),sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    manifest=dict(kind=kind,note='Training inputs for the explicit server projection. Only Current command: lines removed; physical world facts, choices and labels unchanged. Exact projected duplicates removed globally, retaining original split allocations. Development fitting, not independent generalization.',sources=source_hashes,splits=splits,duplicates_removed=dict(removed),builder_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    (output/'manifest.json').write_text(json.dumps(manifest,indent=2));print(json.dumps(manifest,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--data',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--kind',choices=['item','command','enemy'],default='item');a=p.parse_args();build(a.data,a.output,a.kind)
