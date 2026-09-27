"""Offline movement supervision from game observations and explicit teacher examples."""
import argparse,collections,copy,hashlib,json,random,re
from pathlib import Path
from doomlib.movement_questions import with_movement_obstacle_facts


def choose_movement(enemies,clearance,current):
    visible=[e for e in enemies if e.get('visible',True)]
    candidates=visible or enemies
    if not candidates:return 'stationary'
    nearest=min(e['distance'] for e in candidates)
    if nearest<12 and clearance['back']>=4:return 'backward'
    side=current.removeprefix('strafe_') if current in ('strafe_left','strafe_right') else None
    if side is None or clearance[side]<4:side=max(('left','right'),key=lambda k:clearance[k])
    return 'strafe_'+side if clearance[side]>=2 else 'stationary'


def game_rows(run):
    for line in (run/'decisions.jsonl').open():
        d=json.loads(line);p=d['packet']
        if d['directive']['action']!='attack' or 'movement_clearance' not in p:continue
        match=re.search(r'Movement: ([^.]+)',p['state'])
        label=choose_movement(list(p['targets']['enemy'].values()),p['movement_clearance'],match[1] if match else None)
        yield dict(kind='movement',state=p['state'],question=p['questions']['movement'],label=label,category='focused_'+label,
                   source_run=run.name,source_tick=d['tick'],source_episode=d['episode'],source_type='offline_relabel',synthetic=False)


def teacher_rows(run):
    for line in (run/'examples.jsonl').open():
        row=json.loads(line)
        if row['kind']!='movement':continue
        clearance={}
        for key,side in [('strafe_left','left'),('strafe_right','right'),('backward','back')]:
            clearance[side]=float(re.search(r'Body clearance in this direction: ([0-9.]+)m',row['question']['criteria'][key])[1])
        p=with_movement_obstacle_facts(dict(questions={'movement':row['question']},movement_clearance=clearance))
        row['question']=p['questions']['movement'];row['category']='focused_'+row['label'];yield row


def build(train_runs,validation_runs,teacher,replay,output):
    if output.exists():raise ValueError('Output exists')
    if set(train_runs)&set(validation_runs):raise ValueError('Run overlaps splits')
    if teacher in validation_runs:raise ValueError('Teacher overlaps validation')
    sources={};out={};seen={};rng=random.Random(7316)
    for split,runs in [('train',train_runs),('validation',validation_runs)]:
        rows=[]
        for run in runs:
            path=run/'decisions.jsonl';sources[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest();rows.extend(game_rows(run))
        if split=='train':
            path=teacher/'examples.jsonl';sources[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest();rows.extend(teacher_rows(teacher))
        pools=collections.defaultdict(list)
        for row in rows:pools[row['category']].append(row)
        rows=[]
        for values in pools.values():rng.shuffle(values);rows+=values[:350 if split=='train' else 150]
        path=replay/(split+'.json');sources[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
        old=[r for r in json.loads(path.read_text()) if r['kind']=='movement'];rng.shuffle(old)
        for row in old[:200 if split=='train' else 80]:
            row=copy.deepcopy(row);row['category']='map02_replay';rows.append(row)
        clean=[]
        for row in rows:
            key=json.dumps([row['state'],row['question']],sort_keys=True)
            if key in seen:continue
            if row['label'] not in row['question']['criteria']:raise ValueError('Label unavailable')
            seen[key]=(split,row['label']);clean.append(row)
        rng.shuffle(clean);out[split]=clean
    output.mkdir();manifest=dict(note='Offline labels: retreat from threats within 12m when at least 4m body clearance exists, otherwise retain a safe strafe or choose a clear side. Teacher examples from a complete offline run; runtime teacher is not used. Different recorded runs held out, same-map development only. MAP02 replay retained; no live survival claim.',sources=sources,splits={})
    for split,rows in out.items():
        p=output/(split+'.json');p.write_text(json.dumps(rows,indent=2));manifest['splits'][split]=dict(rows=len(rows),sha256=hashlib.sha256(p.read_bytes()).hexdigest(),categories=dict(collections.Counter(r['category'] for r in rows)))
    manifest['builder_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest();(output/'manifest.json').write_text(json.dumps(manifest,indent=2));print(json.dumps(manifest,indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--train-runs',nargs='+',type=Path,required=True);p.add_argument('--validation-runs',nargs='+',type=Path,required=True);p.add_argument('--teacher',type=Path,required=True);p.add_argument('--replay',type=Path,default=Path('training/map2-explicit-movement-v1'));p.add_argument('--output',type=Path,required=True);a=p.parse_args();build(a.train_runs,a.validation_runs,a.teacher,a.replay,a.output)
