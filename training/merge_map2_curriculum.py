"""Merge recorded supervised questions, retaining newer corrections on duplicates."""
import argparse,hashlib,json,random,re,sys,collections
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from decision_questions import compact_state
p=argparse.ArgumentParser();p.add_argument('--sources',nargs='+',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
a.output.mkdir(exist_ok=False);manifest={'sources':[str(x) for x in a.sources],'source_hashes':{},'splits':{}};train_keys=set()
for split in ('train','validation'):
    merged={}
    for source in a.sources:
        path=source/(split+'.json');manifest['source_hashes'][str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
        for original in json.loads(path.read_text()):
            row=dict(original,state=compact_state(original['state']))
            if row['kind']=='movement' and row['label']=='stationary':
                walls=re.search(r'left ([0-9.]+)m, right ([0-9.]+)m',row['state'])
                if walls:row['label']='strafe_left' if float(walls[1])>=float(walls[2]) else 'strafe_right'
            key=json.dumps([row['state'],row['question']],sort_keys=True)
            if split=='validation' and key in train_keys:continue
            merged[key]=row
    if split=='train':train_keys=set(merged)
    rows=list(merged.values());random.Random(991).shuffle(rows)
    path=a.output/(split+'.json');path.write_text(json.dumps(rows,indent=2))
    manifest['splits'][split]={'rows':len(rows),'sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'kinds':dict(collections.Counter(r['kind'] for r in rows))}
    print(split,manifest['splits'][split],flush=True)
(a.output/'manifest.json').write_text(json.dumps(manifest,indent=2))
