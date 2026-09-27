"""Offline target-continuation labels on recorded observations, never live rules."""
import argparse,collections,copy,hashlib,json,random
from pathlib import Path
from doomlib.enemy_commitment import recorded_facts,with_enemy_commitment
from doomlib.decision_questions import with_enemy_visibility_facts
from training.build_map3_combat import gold

def label(packet,facts):
    enemies=packet['targets']['enemy']
    normal=next(v for kind,v,_ in gold(packet,rapid_fire=True) if kind=='enemy')
    current=str(facts['target_id'])
    if current in enemies and facts['age_seconds'] is not None and facts['age_seconds']<1.0:
        urgent=any(e['distance']<1.5 for k,e in enemies.items() if k!=current) and enemies[current]['distance']>5
        if not urgent:return current,'recent_target'
    return normal,'visible_priority'

def build(runs,replay,output):
    if output.exists():raise ValueError('Output exists')
    pools={s:collections.defaultdict(list) for s in ('train','validation')};sources={}
    for run in runs:
        path=run/'decisions.jsonl';sources[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
        decisions=[json.loads(line) for line in path.read_text().splitlines()];facts=recorded_facts(decisions)
        for d in decisions:
            if len(d['packet'].get('targets',{}).get('enemy',{}))<2:continue
            split='validation' if d['episode']%3==0 else 'train'
            for variant,f in [('recorded_acceptance',facts[d['directive']['decision_id']]),('no_active_attack',dict(target_id=None,age_seconds=None))]:
                p=with_enemy_commitment(with_enemy_visibility_facts(d['packet']),f);answer,category=label(p,f)
                row=dict(kind='enemy',state=p['state'],question=p['questions']['enemy'],label=answer,category=category,
                         source_run=run.name,source_tick=d['tick'],source_episode=d['episode'],synthetic=variant!='recorded_acceptance',
                         source_type=variant,enemy_commitment=f)
                pools[split][category].append(row)
    rng=random.Random(9314);out={};seen={}
    for split in ('train','validation'):
        rows=[]
        for category,values in pools[split].items():
            rng.shuffle(values);rows+=values[:500 if split=='train' else 200]
        path=replay/(split+'.json');sources[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
        old=[r for r in json.loads(path.read_text()) if r['kind']=='enemy'];rng.shuffle(old)
        for r in old[:150 if split=='train' else 60]:
            r=copy.deepcopy(r);p=with_enemy_commitment(dict(questions={'enemy':r['question']}),dict(target_id=None,age_seconds=None));r['question']=p['questions']['enemy'];r['category']='replay';r['synthetic']=True;r['source_type']='replay_without_current_attack';rows.append(r)
        clean=[]
        for r in rows:
            key=json.dumps([r['state'],r['question']],sort_keys=True)
            if key in seen:
                if seen[key]!=r['label']:raise ValueError('Conflicting labels')
                continue
            seen[key]=r['label'];clean.append(r)
        rng.shuffle(clean);out[split]=clean
    output.mkdir();manifest=dict(note='Offline teacher retains an available model-selected enemy for its first second unless another enemy is within 1.5m and current is farther than 5m. Otherwise prior visible-threat labels. Counterfactual no-active-attack contrasts share their source episode split. Episode modulo 3=0 held out; same-map development, not independent unseen-map validation. No runtime target locking.',sources=sources,splits={})
    for split,rows in out.items():
        p=output/(split+'.json');p.write_text(json.dumps(rows,indent=2));manifest['splits'][split]=dict(rows=len(rows),sha256=hashlib.sha256(p.read_bytes()).hexdigest(),categories=dict(collections.Counter(r['category'] for r in rows)))
    manifest['builder_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest();(output/'manifest.json').write_text(json.dumps(manifest,indent=2));print(json.dumps(manifest,indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('runs',nargs='+',type=Path);p.add_argument('--replay',type=Path,default=Path('training/map3-combat-rapid-v2'));p.add_argument('--output',type=Path,required=True);a=p.parse_args();build(a.runs,a.replay,a.output)
