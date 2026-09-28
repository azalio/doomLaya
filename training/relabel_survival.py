"""Relabel fixed development observations; keep exact input order for frozen-score reuse."""
import argparse
import collections
import copy
import hashlib
import json
from pathlib import Path
from training.route_survival import labels
from doomlib.command_facts import stable_command_facts_input
from training.build_regression_replay import project


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--rubric",choices=("survival","resupply","resupply_balanced","resupply_close_health","visible_resupply","finish"),default="survival");p.add_argument("--kind",choices=("command","item"),default="command");p.add_argument('--data',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--cache',type=Path);p.add_argument('--output-cache',type=Path);a=p.parse_args()
    import importlib
    labeler=importlib.import_module('training.route_'+a.rubric).labels
    from doomlib.compact_item import category_item_input
    if a.output.exists() or (a.output_cache and a.output_cache.exists()):raise ValueError('Output exists')
    rows={split:json.loads((a.data/(split+'.json')).read_text()) for split in ('train','validation')}
    wanted={(r['source_run'],r['source_tick'],r['raw_state']) for group in rows.values() for r in group}
    packets={};sources={}
    for name in sorted({r['source_run'] for group in rows.values() for r in group}):
        path=Path('runs')/name/'decisions.jsonl';sources[str(path)]=digest(path)
        with path.open() as stream:
            for line in stream:
                d=json.loads(line);key=(name,d['tick'],d['packet']['state'])
                if key in wanted:packets[key]=d['packet']
    for path in sorted(Path('fixtures').glob('v031-*-cases.json')):
        used=False
        for case in json.loads(path.read_text())['cases']:
            key=(case['source_run'],case['tick'],case['packet']['state'])
            if key in wanted:packets[key]=case['packet'];used=True
        if used:sources[str(path)]=digest(path)
    changes=collections.Counter();retained={s:[] for s in rows};indices={s:[] for s in rows}
    for split,group in rows.items():
        for index,row in enumerate(group):
            packet=packets[(row['source_run'],row['source_tick'],row['raw_state'])]
            selected=next(((v,c) for k,v,c in labeler(packet) if k==a.kind),None)
            if selected is None:
                if a.kind=='command':raise ValueError('Missing command label')
                continue
            label,category=selected
            if a.kind=='command':
                projected=project(dict(row,state=packet['state'],question=copy.deepcopy(packet['questions']['command'])))
                state,q=stable_command_facts_input(projected['raw_state'],projected['question'])
            else:state,q=category_item_input(packet['state'],packet['questions']['item'])
            if state!=row['state'] or q!=row['question']:raise ValueError('Source input reconstruction differs')
            changes[split]+=label!=row['label'];row['label']=label
            if row['category']!='regression_retention':row['category']=category
            row['source_type']='offline_'+a.rubric+'_relabel'
            retained[split].append(row);indices[split].append(index)
    rows=retained
    a.output.mkdir()
    manifest=dict(source_manifest=json.loads((a.data/'manifest.json').read_text()),sources=sources,
        builder_sha256=digest(Path(__file__)),labeler_sha256=digest(Path('training/route_'+a.rubric+'.py')),changes=dict(changes),splits={},
        rubric=a.rubric,kind=a.kind,input_projection='command-observed-facts-v2-lift-context' if a.kind=='command' else 'item-category-v2',note='Same physical inputs and temporal split, relabeled offline. Item rows without a selected useful item are omitted. Same-map development data only; no held-out generalization claim.')
    for split,group in rows.items():
        path=a.output/(split+'.json');path.write_text(json.dumps(group,indent=2)+'\n')
        manifest['splits'][split]=dict(rows=len(group),sha256=digest(path))
    (a.output/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    if a.cache:
        if not a.output_cache:raise ValueError('--output-cache required')
        cache=json.loads(a.cache.read_text())
        for split in rows:
            if cache['identity']['data'][split]!=digest(a.data/(split+'.json')):raise ValueError('Original semantic cache differs')
        field='answers' if a.kind=='command' else 'probabilities'
        cache[field]={s:[cache[field][s][i] for i in indices[s]] for s in rows}
        cache['identity']['data']={s:manifest['splits'][s]['sha256'] for s in rows}
        cache['relabel_provenance']=dict(original_cache_sha256=digest(a.cache),inputs_unchanged_verified=True,relabel_manifest_sha256=digest(a.output/'manifest.json'))
        a.output_cache.write_text(json.dumps(cache,indent=2)+'\n')
    print(json.dumps(dict(changes=dict(changes),splits=manifest['splits']),indent=2))

if __name__=='__main__':main()
