"""Offline movement labels that keep a direction while two meters remain clear."""
import argparse,collections,copy,hashlib,json
from pathlib import Path
from doomlib.compact_movement import FORMAT,compact_movement_input,movement_facts


def choose_retained(enemies,clearance,current):
    candidates=[e for e in enemies if e.get('visible',True)] or enemies
    if not candidates:return 'stationary'
    nearest=min(e['distance'] for e in candidates)
    if nearest<12 and clearance['back']>=4:return 'backward'
    side={'strafe_left':'left','strafe_right':'right'}.get(current)
    if side and clearance[side]>=2:return current
    side=max(('left','right'),key=lambda k:clearance[k])
    return 'strafe_'+side if clearance[side]>=2 else 'stationary'


def build(source,output):
    if output.exists():raise ValueError('Output exists')
    result={};seen=set();removed=collections.Counter();changed=collections.Counter();sources={}
    for split in ('train','validation'):
        path=source/(split+'.json');sources[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest();result[split]=[]
        for original in json.loads(path.read_text()):
            if original['category']=='map02_replay':continue
            row=copy.deepcopy(original);facts=movement_facts(row['state'],row['question'])
            label=choose_retained([dict(distance=facts['nearest'],visible=True)],facts['clearance'],facts['current'])
            row['raw_state']=row['state'];row['raw_question']=copy.deepcopy(row['question'])
            row['state'],row['question']=compact_movement_input(row['state'],row['question'])
            key=json.dumps([row['state'],row['question']],sort_keys=True)
            if key in seen:removed[split]+=1;continue
            seen.add(key);changed[split]+=label!=row['label'];row.update(label=label,category='retained_'+label,source_type='offline_relabel');result[split].append(row)
    output.mkdir();manifest=dict(question_format=FORMAT,note='Offline supervision only: preserve the earlier priority of retreating from threats within 12m when 4m behind are clear; otherwise keep the current lateral direction while 2m remain clear. The prior lateral threshold was 4m. Same recorded MAP03 states; no runtime action rule. Rounded textual facts define labels. MAP02 replay excluded; projected duplicates removed train-first. Same-map development, not gameplay proof.',sources=sources,splits={},changed_labels=dict(changed),removed=dict(removed),builder_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    for split,rows in result.items():
        p=output/(split+'.json');p.write_text(json.dumps(rows,indent=2));manifest['splits'][split]=dict(rows=len(rows),sha256=hashlib.sha256(p.read_bytes()).hexdigest(),categories=dict(collections.Counter(r['category'] for r in rows)))
    (output/'manifest.json').write_text(json.dumps(manifest,indent=2));print(json.dumps(manifest,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--data',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();build(a.data,a.output)
