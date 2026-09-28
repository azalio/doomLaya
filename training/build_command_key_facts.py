"""Offline key-observation curriculum with global color contrasts and route retention."""
import argparse,collections,copy,hashlib,json,random,re
from pathlib import Path
from doomlib.command_keys import command_key_input,FORMAT
from training.build_regression_replay import project,resource_examples
from training.route_priority import labels


def project_keys(source):
    row=project(source)
    row['state'],row['question']=command_key_input(row['raw_state'],row['question'])
    return row


def recolor(row,mapping):
    result=copy.deepcopy(row)
    def change(text):
        text=re.sub(r'(Blue|Red|Yellow)(Card|Skull)',lambda m:mapping[m[1].lower()].title()+m[2],text)
        return re.sub(r'\b(blue|red|yellow)\b',lambda m:mapping[m[1]],text)
    result['raw_state']=change(result['raw_state']);result['state']=change(result['state'])
    result.update(category='key_color_contrast_'+row['label'],synthetic=True,source_type='global_key_color_permutation',color_permutation=mapping)
    return result


def build(replay,failure,success,cases,answers,output):
    if output.exists():raise ValueError('Output exists')
    rng=random.Random(271113);sources={};pools={s:[] for s in ('train','validation')};seen={};removed=collections.Counter()
    def read(path,jsonl=False):
        sources[str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
        return [json.loads(l) for l in path.open()] if jsonl else json.loads(path.read_text())
    for split in pools:
        pools[split].extend(read(replay/(split+'.json')))
    for d in read(failure/'decisions.jsonl',True):
        packet=d['packet']
        if not any(v.get('category')=='Key' and v.get('reachable') for v in packet.get('targets',{}).get('item',{}).values()):continue
        split='validation' if d['tick']//700%5==0 else 'train'
        for row in resource_examples(packet,failure.name,d['tick'],d['episode'],labels):
            if row['kind']=='command':row['category']='key_observed_'+row['label'];pools[split].append(row)
    for d in read(success/'decisions.jsonl',True):
        if d['episode']!=0:continue
        a=d['answers']['command'];label=a.get('look_gate',{}).get('base_answer',a)['choice'];split='validation' if d['tick']//700%5==0 else 'train'
        pools[split].append(dict(kind='command',label=label,category='latest_map01_'+label,state=d['packet']['state'],question=copy.deepcopy(d['packet']['questions']['command']),source_run=success.name,source_tick=d['tick'],source_type='behavior_replay_completed_map01',synthetic=False))
    fixture=read(cases)['cases'];results=read(answers)['results']
    if len(fixture)!=len(results) or not all(r['passed'] for r in results):raise ValueError('Expected passing retention cases')
    for case,result in zip(fixture,results):
        if (case['source_run'],case['tick'])!=(result['source_run'],result['tick']):raise ValueError('Probe order differs')
        a=result['answers']['command'];label=a.get('look_gate',{}).get('base_answer',a)['choice'];pools['train'].append(dict(kind='command',label=label,category='retention_probe',state=case['packet']['state'],question=copy.deepcopy(case['packet']['questions']['command']),source_run=case['source_run'],source_tick=case['tick'],source_type='development_probe_retention',synthetic=False))
    output.mkdir();manifest=dict(note='Adds an explicit factual list of reachable keys, no action advice or action mask. MAP02 key-state corrections plus successful MAP01 replay and the prior route curriculum. Source 20-second temporal development blocks remain correlated; 29 old passing probes are training retention. Global bijective key-color permutations change object names, collected-key facts and mechanism route-key facts together. Live gameplay remains a separate gate.',input_projection=FORMAT,sources=sources,splits={},builder_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),projection_sha256=hashlib.sha256(Path('doomlib/command_keys.py').read_bytes()).hexdigest())
    for split in ('train','validation'):
        groups=collections.defaultdict(list)
        for source in pools[split]:groups[source['category']].append(source)
        rows=[]
        for category,group in groups.items():
            rng.shuffle(group)
            cap=180 if split=='train' else 60
            if category in ('near_lift_regression','completed_mechanisms_exit'):cap=200 if split=='train' else 70
            for source in group[:cap]:
                row=project_keys(source);rows.append(row)
                if category.startswith('key_observed_'):
                    for mapping in ({'blue':'yellow','yellow':'red','red':'blue'},{'blue':'red','red':'yellow','yellow':'blue'}):rows.append(recolor(row,mapping))
        rows.sort(key=lambda r:not r['category'].startswith(('key_observed','key_color')))
        clean=[]
        for row in rows:
            key=json.dumps([row['state'],row['question']],sort_keys=True)
            if key in seen:removed[split+('_conflict' if seen[key]!=row['label'] else '_duplicate')]+=1;continue
            seen[key]=row['label'];clean.append(row)
        rng.shuffle(clean);path=output/(split+'.json');path.write_text(json.dumps(clean,indent=2));manifest['splits'][split]=dict(rows=len(clean),sha256=hashlib.sha256(path.read_bytes()).hexdigest(),categories=dict(collections.Counter(r['category'] for r in clean)))
    manifest['removed']=dict(removed);(output/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n');print(json.dumps(manifest['splits'],indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('replay','failure','success','cases','answers','output'):p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();build(a.replay,a.failure,a.success,a.cases,a.answers,a.output)
