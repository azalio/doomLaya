"""Project recorded MAP03 movement examples to compact factual inputs."""
import argparse, collections, copy, hashlib, json
from pathlib import Path
from doomlib.compact_movement import FORMAT, compact_movement_input, movement_facts
from training.build_map3_retreat import choose_movement


def build(source, output):
    if output.exists(): raise ValueError('Output exists')
    seen={};result={};removed=collections.Counter();sources={}
    for split in ('train','validation'):
        path=source/(split+'.json');sources[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest();result[split]=[]
        for original in json.loads(path.read_text()):
            if original['category']=='map02_replay':continue
            facts=movement_facts(original['state'],original['question'])
            expected=choose_movement([dict(distance=facts['nearest'],visible=True)],facts['clearance'],facts['current'])
            if original['label']!=expected:
                if facts['nearest']==12 and original['label']=='backward':
                    removed['rounded_distance_boundary']+=1;continue
                raise ValueError('Recorded label and compact facts disagree: '+str((original['source_run'],original['source_tick'],original['label'],expected)))
            row=copy.deepcopy(original);row['state'],row['question']=compact_movement_input(row['state'],row['question'])
            key=json.dumps([row['state'],row['question']],sort_keys=True)
            if key in seen:
                if seen[key][1]!=row['label']:raise ValueError('Conflicting effective facts')
                removed[split]+=1;continue
            seen[key]=(split,row['label']);result[split].append(row)
    output.mkdir();manifest=dict(question_format=FORMAT,note='Same MAP03 observed states and offline retreat labels, projected to combat geometry only. MAP02 replay excluded. Numeric distances and factual threshold comparisons are provided; every explicit movement remains available. Repeated projected inputs removed train-first; ambiguous rounded 12m boundary rows excluded. Held-out source run is same-map development, not gameplay proof.',sources=sources,splits={},removed=dict(removed),builder_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),projection_sha256=hashlib.sha256(Path('doomlib/compact_movement.py').read_bytes()).hexdigest())
    for split,rows in result.items():
        path=output/(split+'.json');path.write_text(json.dumps(rows,indent=2));manifest['splits'][split]=dict(rows=len(rows),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),categories=dict(collections.Counter(row['category'] for row in rows)))
    (output/'manifest.json').write_text(json.dumps(manifest,indent=2));print(json.dumps(manifest,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--data',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();build(a.data,a.output)
