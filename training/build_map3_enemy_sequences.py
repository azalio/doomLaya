"""Offline supervision for explicit enemy firing sequences; never live tactics."""
import argparse,collections,copy,hashlib,json,random
from pathlib import Path
from doomlib.enemy_sequences import with_enemy_sequences,QUESTION_FORMAT


def order_for(packet,first=None):
    enemies=packet['targets']['enemy'];visible={k:e for k,e in enemies.items() if e.get('visible',True)};candidates=visible or enemies
    def weight(k):return enemies[k]['distance']*(.65 if enemies[k]['name'] in ('ShotgunGuy','Zombieman','ChaingunGuy') else 1)
    if first is None:
        first=min(candidates,key=lambda k:weight(k)+abs(enemies[k].get('bearing',0))/30)
        current=str((packet.get('enemy_commitment') or {}).get('target_id'))
        if current in visible and not (enemies[first]['distance']<1.5 and enemies[current]['distance']>5):first=current
    if first not in enemies:raise ValueError('Teacher target is not observed')
    return [first]+sorted((k for k in enemies if k!=first),key=weight)


def examples(packet,order,provenance):
    keys=list(packet['targets']['enemy'])
    for presentation in (keys,list(reversed(keys))):
        p=copy.deepcopy(packet);p['targets']['enemy']={k:p['targets']['enemy'][k] for k in presentation};p=with_enemy_sequences(p)
        key=next(k for k,v in p['enemy_sequences'].items() if v==order)
        state='\n'.join(l for l in p['state'].splitlines() if not l.startswith('Current command:'))
        yield dict(provenance,kind='enemy',state=state,question=p['questions']['enemy'],label=key,category='full_'+str(len(order)),ordered_target_ids=order,enemy_sequences=p['enemy_sequences'],synthetic=presentation!=keys)


def recorded(run):
    for line in (run/'decisions.jsonl').open():
        d=json.loads(line);p=d['packet']
        if d['directive']['action']!='attack' or len(p['targets'].get('enemy',{}))<2:continue
        yield p,order_for(p),dict(source_run=run.name,source_tick=d['tick'],source_episode=d['episode'],source_type='offline_relabel')


def teacher(run):
    groups={}
    for line in (run/'examples.jsonl').open():
        r=json.loads(line);groups.setdefault(r['source_tick'],{})[r['kind']]=r
    states={}
    for line in (run/'telemetry.jsonl').open():
        r=json.loads(line)
        if r['tick'] in groups:states[r['tick']]=r
    delay=json.loads((run/'summary.json').read_text())['latency_ticks'];timeline=sorted(groups);index=0;latest=None
    for tick in timeline:
        while index<len(timeline) and timeline[index]+delay<=tick:
            old=groups[timeline[index]];latest=int(old['enemy']['label']) if old['command']['label']=='attack' else None;index+=1
        group=groups[tick]
        if 'enemy' not in group:continue
        r=group['enemy'];keys=list(r['question']['criteria']);s=states[tick];targets={str(e['id']):e for e in s['enemies'] if str(e['id']) in keys}
        if len(targets)<2:continue
        if set(targets)!=set(keys):raise ValueError('Teacher labels do not match observed actors')
        p=dict(state=r['state'],questions={'enemy':r['question']},targets={'enemy':targets},enemy_commitment={'target_id':latest,'age_seconds':None})
        yield p,order_for(p,r['label']),dict(source_run=run.name,source_tick=tick,source_episode=r['source_episode'],source_type='offline_teacher')


def build(train_runs,validation_runs,teacher_run,output):
    if output.exists():raise ValueError('Output exists')
    if set(train_runs)&set(validation_runs):raise ValueError('Run overlaps splits')
    rng=random.Random(7361);sources={};out={};seen={}
    for split,runs in [('train',train_runs),('validation',validation_runs)]:
        candidates=[]
        for run in runs:
            path=run/'decisions.jsonl';sources[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest();candidates+=list(recorded(run))
        rng.shuffle(candidates);candidates=candidates[:500 if split=='train' else 200]
        if split=='train':
            for name in ('examples.jsonl','telemetry.jsonl','summary.json'):
                path=teacher_run/name;sources[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
            candidates+=list(teacher(teacher_run))
        rows=[]
        for packet,order,provenance in candidates:
            for row in examples(packet,order,provenance):
                key=json.dumps([row['state'],row['question']],sort_keys=True)
                if key in seen:
                    if seen[key]!=row['label']:raise ValueError('Conflicting labels')
                    continue
                seen[key]=row['label'];rows.append(row)
        rng.shuffle(rows);out[split]=rows
    output.mkdir();manifest=dict(question_format=QUESTION_FORMAT,note='Offline full ordered-plan labels, all nonempty ordered subsets remain model options. First target: keep the previous visible target unless a point-blank threat, otherwise prioritize visible shooters and bearing; remaining known actors ordered by weighted distance. Teacher first target copied from recorded successful offline rollout. Candidate-order reversals share the same split. Separate recorded runs held out; same-map development, not unseen-map validation.',sources=sources,splits={})
    for split,rows in out.items():
        p=output/(split+'.json');p.write_text(json.dumps(rows,indent=2));manifest['splits'][split]=dict(rows=len(rows),sha256=hashlib.sha256(p.read_bytes()).hexdigest(),categories=dict(collections.Counter(r['category'] for r in rows)))
    manifest['builder_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest();manifest['formatter_sha256']=hashlib.sha256(Path('doomlib/enemy_sequences.py').read_bytes()).hexdigest();(output/'manifest.json').write_text(json.dumps(manifest,indent=2));print(json.dumps(manifest,indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--train-runs',type=Path,nargs='+',required=True);p.add_argument('--validation-runs',type=Path,nargs='+',required=True);p.add_argument('--teacher',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();build(a.train_runs,a.validation_runs,a.teacher,a.output)
