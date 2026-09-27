"""Learn mechanism choices from a completed mechanics fixture and MAP02 replay."""
import argparse,collections,copy,hashlib,json,random
from pathlib import Path


def build(run,replay,output):
    if output.exists():raise ValueError('Output exists')
    summary=json.loads((run/'summary.json').read_text())
    if not summary.get('map_completed') or not summary.get('no_monsters'):raise ValueError('A completed mechanics fixture is required')
    manifest=dict(note='MAP03 no-monsters route demonstration, not gameplay by Laya. Split into four-second time blocks: every fifth block is validation; nearby states are correlated. Goal variants stay in their parent split. MAP02 replay preserves its existing allocation. This measures development fitting, not generalization.',sources={str(run/name):hashlib.sha256((run/name).read_bytes()).hexdigest() for name in ('config.json','summary.json','examples.jsonl')},splits={})
    pools={'train':[],'validation':[]}
    for row in map(json.loads,(run/'examples.jsonl').read_text().splitlines()):
        if row['kind']!='switch':continue
        split='validation' if row['source_tick']//140%5==0 else 'train'
        row=copy.deepcopy(row);row['category']='map03_route';pools[split].append(row)
        variant=copy.deepcopy(row);lines=variant['state'].splitlines()
        variant['state']='\n'.join(line for line in lines if not line.startswith(('Current command:','Previous command result:')))
        variant.update(synthetic=True,source_type='counterfactual_goal')
        pools[split].append(variant)
    rng=random.Random(9304);seen={};output.mkdir()
    for split in ('train','validation'):
        path=replay/(split+'.json');manifest['sources'][str(path)]=hashlib.sha256(path.read_bytes()).hexdigest()
        replay_rows=[r for r in json.loads(path.read_text()) if r['kind']=='switch'];rng.shuffle(replay_rows)
        rows=pools[split]+replay_rows[:400 if split=='train' else 150]
        clean=[]
        for row in rows:
            key=json.dumps([row['state'],row['question']],sort_keys=True)
            if key in seen:
                if seen[key]!=row['label']:raise ValueError('Conflicting labels')
                continue
            seen[key]=row['label'];clean.append(row)
        rng.shuffle(clean);p=output/(split+'.json');p.write_text(json.dumps(clean,indent=2));manifest['splits'][split]=dict(rows=len(clean),sha256=hashlib.sha256(p.read_bytes()).hexdigest(),labels=dict(collections.Counter(r['label'] for r in clean)),source_types=dict(collections.Counter(r.get('source_type','legacy') for r in clean)))
    manifest['builder_sha256']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest();(output/'manifest.json').write_text(json.dumps(manifest,indent=2));print(json.dumps(manifest,indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('run',type=Path);p.add_argument('--replay',type=Path,default=Path('training/map2-stable-goals-v1'));p.add_argument('--output',type=Path,required=True);a=p.parse_args();build(a.run,a.replay,a.output)
