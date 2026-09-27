"""Offline look-back supervision from recorded health loss, plus labeled contrasts."""
import argparse,collections,copy,hashlib,json,random
from pathlib import Path
from doomlib.look_questions import DamageHistory,look_question
from training.build_map3_resources import labels

NONE=dict(hp_loss=0,latest_age_seconds=None,looked_after_hit=False)


def build(run,replay,output):
    if output.exists():raise ValueError('Output exists')
    decisions={d['tick']:d for d in map(json.loads,(run/'decisions.jsonl').read_text().splitlines())}
    history=DamageHistory();pools={s:collections.defaultdict(list) for s in ('train','validation')}
    for line in (run/'telemetry.jsonl').open():
        state=json.loads(line);tick=state['tick'];facts=history.observe(state,tick,state['episode'])
        if tick not in decisions:continue
        decision=decisions[tick];packet=decision['packet']
        if decision['episode']!=state['episode']:raise ValueError('Episode mismatch')
        root=next(((label,category) for kind,label,category in labels(packet) if kind=='command'),None)
        if root is None:continue
        original_label,category=root
        split='validation' if state['episode']%3==0 else 'train'
        text='\n'.join(l for l in packet['state'].splitlines() if not l.startswith('Current command:'))
        base=dict(kind='command',state=text,source_run=run.name,source_tick=tick,source_episode=state['episode'],source_type='offline_map03_look_correction',synthetic=False)
        def add(label,group,fact,status='inactive',synthetic=False):
            pools[split][group].append(dict(base,label=label,category=group,question=look_question(packet['questions']['command'],fact,status),look_facts=dict(fact,status=status),synthetic=synthetic))
        unseen=facts['hp_loss']>0 and not packet.get('targets',{}).get('enemy')
        if unseen:
            add('look_back','unseen_damage_look',facts)
            add('look_back','continue_selected_look',facts,'executing',True)
            checked=dict(facts,looked_after_hit=True)
            add(original_label,'completed_look_resume',checked,'arrived',True)
            add(original_label,'checked_hit_resume',checked,'inactive',True)
            add(original_label,'no_recent_hit_resume',NONE,'inactive',True)
        else:
            add(original_label,'observed_'+category,facts)
    rng=random.Random(9312);rows={};sources={}
    for filename in ('decisions.jsonl','telemetry.jsonl'):
        path=run/filename;sources[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
    for split,groups in pools.items():
        rows[split]=[]
        for group in groups.values():
            rng.shuffle(group);rows[split].extend(group[:180 if split=='train' else 60])
        path=replay/(split+'.json');sources[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
        for row in json.loads(path.read_text()):
            if row['kind']!='command':raise ValueError('Command-only replay required')
            row=copy.deepcopy(row);row['question']=look_question(row['question'],NONE)
            row['look_facts']=dict(NONE,status='inactive');row['synthetic']=True
            row['look_context_source']='counterfactual_no_recent_damage'
            rows[split].append(row)
    output.mkdir();seen={};removed=collections.Counter();splits={}
    for split in ('validation','train'):
        clean=[]
        for row in rows[split]:
            key=json.dumps([row['state'],row['question']],sort_keys=True)
            if key in seen:
                if seen[key]!=row['label']:raise ValueError('Conflicting identical inputs')
                removed[split]+=1;continue
            seen[key]=row['label'];clean.append(row)
        rng.shuffle(clean);dest=output/(split+'.json');dest.write_text(json.dumps(clean,indent=2))
        splits[split]=dict(rows=len(clean),sha256=hashlib.sha256(dest.read_bytes()).hexdigest(),categories=dict(collections.Counter(r['category'] for r in clean)))
    manifest=dict(note='Recorded HP drops in a two-second observation window, with look-back label only for no observed/recent enemy. Existing resource teacher supplies other labels. Counterfactual ongoing/completed look and no-recent-hit examples are explicitly synthetic; no gameplay outcome is claimed. All old command replay retained with synthetic no-recent-damage context. Episode modulo 3 held out for fresh records, not independent map validation. Runtime does not contain the label rule.',sources=sources,splits=splits,removed=dict(removed),builder_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    (output/'manifest.json').write_text(json.dumps(manifest,indent=2));print(json.dumps(manifest,indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('run',type=Path);p.add_argument('--replay',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();build(a.run,a.replay,a.output)
