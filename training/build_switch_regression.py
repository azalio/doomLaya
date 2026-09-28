"""Offline MAP02 mechanism corrections with unchanged MAP03 route replay."""
import argparse,collections,copy,hashlib,json,random
from pathlib import Path
from training.build_goal_invariant_switches import change_goal


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def nearest_needed(packet):
    mechanisms=packet['targets']['switch'];current=packet['observation'].get('execution',{})
    riding=[k for k,m in mechanisms.items() if m.get('kind')=='lift' and m.get('phase') in ('board','ride') and m['distance']<5 and current.get('action')=='use_switch' and str(current.get('target_id'))==k]
    return riding[0] if riding else min(mechanisms,key=lambda k:(mechanisms[k]['distance'],k))


def build(run,replay,output):
    if output.exists():raise ValueError('Output exists')
    summary=json.loads((run/'summary.json').read_text())
    if summary['final_map']!='MAP02':raise ValueError('Expected the recorded MAP02 switch-loop run')
    rows={s:json.loads((replay/(s+'.json')).read_text()) for s in ('train','validation')};added=collections.Counter();seen={json.dumps([r['state'],r['question']],sort_keys=True) for group in rows.values() for r in group}
    for index,line in enumerate((run/'decisions.jsonl').open()):
        d=json.loads(line);packet=d['packet'];mechanisms=packet.get('targets',{}).get('switch',{})
        # This correction is bounded to the observed pre-key MAP02 loop.
        if index%8 or d['game_seconds']<145 or d['choice']!='use_switch' or set(mechanisms)!={'662','805'} or 'Collected keys: none.' not in packet['state']:continue
        row=dict(kind='switch',state=packet['state'],question=copy.deepcopy(packet['questions']['switch']),label=nearest_needed(packet),category='map2_switch_loop',source_run=run.name,source_tick=d['tick'],source_episode=d['episode'],source_type='offline_nearest_reachable_mechanism_correction',synthetic=False)
        variants=[row]+[change_goal(row,key) for key in mechanisms]
        split='validation' if d['tick']//140%5==0 else 'train'
        for variant in variants:
            key=json.dumps([variant['state'],variant['question']],sort_keys=True)
            if key in seen:continue
            seen.add(key);rows[split].append(variant);added[split]+=1
    output.mkdir();manifest=dict(builder_sha256=digest(Path(__file__)),sources={str(run/'decisions.jsonl'):digest(run/'decisions.jsonl'),str(replay/'manifest.json'):digest(replay/'manifest.json')},added=dict(added),splits={},note='Same-map development corrections; four-second temporal blocks with every fifth block for validation. Goal variants remain in the same split. Original MAP03 route and MAP02 replay retained. No runtime rule, no held-out-map claim.')
    for s,group in rows.items():
        random.Random(771).shuffle(group);path=output/(s+'.json');path.write_text(json.dumps(group,indent=2)+'\n');manifest['splits'][s]=dict(rows=len(group),sha256=digest(path),categories=dict(collections.Counter(r['category'] for r in group)))
    (output/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n');print(json.dumps(dict(added=dict(added),splits=manifest['splits']),indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--run',type=Path,required=True);p.add_argument('--replay',type=Path,default=Path('training/map3-switch-route-v1'));p.add_argument('--output',type=Path,required=True);a=p.parse_args();build(a.run,a.replay,a.output)
