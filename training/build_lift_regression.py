"""Offline lift-loop correction with behavioral replay of completed MAP01/MAP03."""
import argparse,collections,copy,hashlib,json,random
from pathlib import Path
from training.build_regression_replay import project,resource_examples
from training.route_priority import labels


def build(failure,map01,map03,replay,cases,answers,output):
    if output.exists():raise ValueError('Output exists')
    rng=random.Random(271017);pools={s:[] for s in ('train','validation')};sources={};seen={};removed=collections.Counter()
    def read(path,jsonl=False):
        sources[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
        return [json.loads(l) for l in path.open()] if jsonl else json.loads(path.read_text())
    for run,episode,name in ((map01,0,'map01'),(map03,4,'map03')):
        for d in read(run/'decisions.jsonl',True):
            if d['episode']!=episode:continue
            a=d['answers']['command'];label=a.get('look_gate',{}).get('base_answer',a)['choice']
            row=project(dict(kind='command',label=label,category='replay_completed_'+name+'_'+label,state=d['packet']['state'],question=copy.deepcopy(d['packet']['questions']['command']),source_run=run.name,source_tick=d['tick'],source_episode=episode,source_type='behavior_replay_completed_episode',synthetic=False))
            split='validation' if d['tick']//700%5==0 else 'train';pools[split].append(row)
    for d in read(failure/'decisions.jsonl',True):
        for row in resource_examples(d['packet'],failure.name,d['tick'],d['episode'],labels):
            if row['kind']!='command':continue
            row=project(row);m=d['packet'].get('targets',{}).get('switch',{}).get('805')
            # The selected label stays map-independent; only this diagnostic group
            # identifies the observed near-lift regression for weighted sampling.
            if row['label']=='use_switch' and m and m['distance']<6 and d['game_seconds']>=420:
                row['category']='near_lift_regression'
            else:row['category']='new_run_'+row['category']
            split='validation' if d['tick']//700%5==0 else 'train';pools[split].append(row)
    fixture=read(cases)['cases'];result=read(answers)['results']
    if len(fixture)!=len(result) or not all(r['passed'] for r in result):raise ValueError('Expected passed retention cases')
    for case,answer in zip(fixture,result):
        if (case['source_run'],case['tick'])!=(answer['source_run'],answer['tick']):raise ValueError('Retention case mismatch')
        p=case['packet'];a=answer['answers']['command'];label=a.get('look_gate',{}).get('base_answer',a)['choice']
        pools['train'].append(project(dict(kind='command',label=label,category='retention_regression_cases',state=p['state'],question=copy.deepcopy(p['questions']['command']),source_run=case['source_run'],source_tick=case['tick'],source_type='development_probe_retention',synthetic=False)))
    for split in pools:
        for row in read(replay/(split+'.json')):
            if row['category'] in ('completed_mechanisms_exit','correction_route_missing_key','replay_map3-combat-priority-v2_reachable_red_key_contrast'):
                pools[split].append(row)
    output.mkdir();manifest=dict(note='Corrective labels on the interrupted MAP02 run plus exact normal-command behavioral replay from completed MAP01 episode 0 and MAP03 episode 4. Every fifth 20-second source block is development validation; adjacent blocks are correlated. The 23 prior passing development probes are training retention. Prior exit/key replay keeps its allocation. Not independent generalization; no runtime teacher.',input_projection='without-current-command-v1',sources=sources,splits={},removed={},builder_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),labeler_sha256=hashlib.sha256(Path('training/route_priority.py').read_bytes()).hexdigest())
    for split in ('train','validation'):
        groups=collections.defaultdict(list)
        for r in pools[split]:groups[r['category']].append(r)
        rows=[]
        for category,group in groups.items():
            rng.shuffle(group);cap=(200 if split=='train' else 70) if category in ('near_lift_regression','completed_mechanisms_exit') else (120 if split=='train' else 50)
            rows.extend(group[:cap])
        # New corrective observations precede replay when exactly identical.
        rows.sort(key=lambda r:not r['category'].startswith(('near_lift','new_run')))
        clean=[]
        for r in rows:
            key=json.dumps([r['state'],r['question']],sort_keys=True)
            if key in seen:removed[split+('_conflict' if seen[key]!=r['label'] else '_duplicate')]+=1;continue
            seen[key]=r['label'];clean.append(r)
        rng.shuffle(clean);path=output/(split+'.json');path.write_text(json.dumps(clean,indent=2));manifest['splits'][split]=dict(rows=len(clean),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),categories=dict(collections.Counter(r['category'] for r in clean)))
    manifest['removed']=dict(removed);(output/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n');print(json.dumps(manifest['splits'],indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('failure','map01','map03','replay','cases','answers','output'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();build(a.failure,a.map01,a.map03,a.replay,a.cases,a.answers,a.output)
