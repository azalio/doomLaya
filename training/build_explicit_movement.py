"""Merge movement datasets after replacing duplicate continuation labels."""
import argparse
import collections
import hashlib
import json
import random
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from doomlib.movement_questions import explicit_example


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--sources',nargs='+',type=Path,required=True)
    p.add_argument('--output',type=Path,required=True)
    a=p.parse_args()
    if a.output.exists():p.error('output exists')
    seen={};splits={};manifest=dict(note='Offline explicit movement targets. All four physical choices preserved; duplicate continuation removed. No held-out death-window rows.',sources={},splits={})
    for split in ('train','validation'):
        rows=[]
        for source in a.sources:
            path=source/(split+'.json');manifest['sources'][str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
            for original in json.loads(path.read_text()):
                if original['kind']!='movement':continue
                row=explicit_example(original)
                key=json.dumps([row['state'],row['question']],sort_keys=True)
                if key in seen:
                    if seen[key]!=row['label']:raise ValueError('Conflicting explicit labels')
                    continue
                seen[key]=row['label'];rows.append(row)
        random.Random(71121 if split=='train' else 71122).shuffle(rows)
        splits[split]=rows
        manifest['splits'][split]=dict(rows=len(rows),labels=dict(collections.Counter(r['label'] for r in rows)))
    a.output.mkdir()
    for split,rows in splits.items():
        path=a.output/(split+'.json');path.write_text(json.dumps(rows,indent=2))
        manifest['splits'][split]['sha256']=hashlib.sha256(path.read_bytes()).hexdigest()
    (a.output/'manifest.json').write_text(json.dumps(manifest,indent=2))
    print(json.dumps(manifest,indent=2))


if __name__=='__main__':main()
