"""Convert frozen flat commands into independently labeled model decisions."""
import argparse
import hashlib
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from doomlib.decision_questions import questions,split_command,TARGET_TYPES,state_text

p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
a.output.mkdir(parents=True,exist_ok=False)
manifest={'source':str(a.source),'decision_format':'factorized','source_sha256':{}}
for split in ('train','validation'):
    source=a.source/(split+'.json');manifest['source_sha256'][split]=hashlib.sha256(source.read_bytes()).hexdigest();records=[]
    for row in json.loads(source.read_text()):
        if row['kind']=='weapon':records.append(row);continue
        qs=questions(row['question']['criteria']);action,target,movement=split_command(row['label']);labels={'command':action}
        if action in TARGET_TYPES:labels[TARGET_TYPES[action]]=target
        if action=='attack':labels['movement']=movement
        for kind,label in labels.items():
            assert label in qs[kind]['criteria']
            records.append(dict(row,state=state_text(row['state'],row['question']['criteria']),kind=kind,label=label,question=qs[kind],flat_label=row['label']))
    target=a.output/(split+'.json');target.write_text(json.dumps(records,indent=2))
    manifest[split]={'rows':len(records),'sha256':hashlib.sha256(target.read_bytes()).hexdigest()};print(split,manifest[split],flush=True)
(a.output/'manifest.json').write_text(json.dumps(manifest,indent=2))
