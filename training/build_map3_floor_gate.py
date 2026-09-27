"""Add mapped-floor contrasts to the observed-damage look gate; offline labels only."""
import argparse,copy,collections,hashlib,json,random
from pathlib import Path
from doomlib.look_questions import look_gate_input


def build(source,output):
    if output.exists():raise ValueError('Output exists')
    output.mkdir();manifest=dict(note='Each original look-gate row remains in its original split, together with safe-floor and damaging-floor variants. Damaging-floor labels choose normal command selection. No action is forced at inference. Synthetic observation-domain validation only; no gameplay/generalization claim.',sources={},splits={})
    for split in ('train','validation'):
        path=source/(split+'.json');manifest['sources'][str(path)]=hashlib.sha256(path.read_bytes()).hexdigest();rows=[]
        for original in json.loads(path.read_text()):
            rows.append(original)
            for floor in (False,True):
                row=copy.deepcopy(original);row['look_facts']['standing_on_damaging_floor']=floor
                row['state'],row['question']=look_gate_input(row['look_facts'])
                if floor:row.update(label='normal',category='floor_damage')
                row['source_type']='synthetic_observed_look_floor_facts';rows.append(row)
        random.Random(9317).shuffle(rows);dest=output/(split+'.json');dest.write_text(json.dumps(rows,indent=2));manifest['splits'][split]=dict(rows=len(rows),sha256=hashlib.sha256(dest.read_bytes()).hexdigest(),categories=dict(collections.Counter(r['category'] for r in rows)))
    manifest['builder_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    (output/'manifest.json').write_text(json.dumps(manifest,indent=2));print(json.dumps(manifest,indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,default=Path('training/map3-look-gate-balanced-v1'));p.add_argument('--output',type=Path,required=True);a=p.parse_args();build(a.source,a.output)
