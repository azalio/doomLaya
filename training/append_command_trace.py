"""Append relabeled on-policy observations with their verified frozen semantic scores."""
import argparse,copy,hashlib,json
from pathlib import Path
from doomlib.command_facts import STABLE_FORMAT,stable_command_facts_input
from training.build_regression_replay import project
from training.route_resupply import labels


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('data','cache','output','output-cache'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--run',type=Path,action='append',required=True)
    p.add_argument('--close-health-labels',action='store_true')
    p.add_argument('--visible-fight-labels',action='store_true')
    p.add_argument('--finish-route-labels',action='store_true')
    p.add_argument('--all-errors',action='store_true',help='Keep every distinct misclassified observation; retain the usual sample of correct responses')
    p.add_argument('--min-seconds',type=float,default=0)
    p.add_argument('--only-category',action='append',help='Append only these offline label categories')
    p.add_argument('--category-prefix',default='',help='Mark appended corrections for selective training')
    a=p.parse_args()
    if sum((a.close_health_labels,a.visible_fight_labels,a.finish_route_labels))>1:p.error('Choose one rubric')
    labeler=labels
    if a.close_health_labels:
        from training.route_resupply_close_health import labels as labeler
    if a.visible_fight_labels:
        if a.close_health_labels:p.error('Choose one rubric')
        from training.route_visible_resupply import labels as labeler
    if a.finish_route_labels:
        from training.route_finish import labels as labeler
    if a.output.exists() or a.output_cache.exists():raise ValueError('Output exists')
    rows={s:json.loads((a.data/(s+'.json')).read_text()) for s in ('train','validation')}
    cache=json.loads(a.cache.read_text())
    for s in rows:
        if cache['identity']['data'][s]!=digest(a.data/(s+'.json')):raise ValueError('Cache data differs')
    seen={json.dumps([r['state'],r['question']],sort_keys=True) for group in rows.values() for r in group}
    added={s:0 for s in rows};sources={}
    for run in a.run:
        if not (run/'summary.json').exists():raise ValueError('Only finalized traces may be appended')
        decisions=[json.loads(line) for line in (run/'decisions.jsonl').open()]
        cutoff=decisions[-1]['tick']*.8;sources[str(run/'decisions.jsonl')]=digest(run/'decisions.jsonl')
        for index,d in enumerate(decisions):
            packet=d['packet'];gold,category=next((v,c) for k,v,c in labeler(packet) if k=='command')
            if d['tick']/35<a.min_seconds or (a.only_category and category not in a.only_category):continue
            answer=d['answers']['command'];base=answer.get('look_gate',{}).get('base_answer',answer)
            if gold==base['choice']:
                if index%24:continue
            elif not a.all_errors and index%6:continue
            head=d['routing']['question_heads']['command']
            if head['weights_sha256']!=cache['identity']['semantic_weights'] or head['input_projection']!=STABLE_FORMAT:raise ValueError('Frozen head differs')
            semantic=base['numeric_residual']['semantic_answer']
            row=dict(kind='command',label=gold,category=a.category_prefix+category,state=packet['state'],question=copy.deepcopy(packet['questions']['command']),source_run=run.name,source_tick=d['tick'],source_episode=d['episode'],source_type='offline_on_policy_resupply_relabel',synthetic=False)
            row=project(row);row['state'],row['question']=stable_command_facts_input(row['raw_state'],row['question'])
            if set(semantic['probabilities'])!=set(row['question']['criteria']):raise ValueError('Semantic options differ')
            key=json.dumps([row['state'],row['question']],sort_keys=True)
            if key in seen:continue
            seen.add(key);split='train' if d['tick']<cutoff else 'validation';rows[split].append(row);cache['answers'][split].append(dict(probabilities=semantic['probabilities']));added[split]+=1
    labeler_path=Path(__import__(labeler.__module__,fromlist=['labels']).__file__)
    a.output.mkdir();manifest=dict(builder_sha256=digest(Path(__file__)),labeler_sha256=digest(labeler_path),labeler=labeler.__module__,all_errors=a.all_errors,source_manifest=json.loads((a.data/'manifest.json').read_text()),sources=sources,added=added,splits={},note='On-policy same-map development corrections; temporal 80/20 split within each run. No held-out-map claim. Frozen semantic scores come from recorded API responses, not the corrected labels.')
    manifest['selection']=dict(min_seconds=a.min_seconds,only_categories=a.only_category,category_prefix=a.category_prefix)
    for s,group in rows.items():
        path=a.output/(s+'.json');path.write_text(json.dumps(group,indent=2)+'\n');manifest['splits'][s]=dict(rows=len(group),sha256=digest(path))
    (a.output/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    cache['identity']['data']={s:manifest['splits'][s]['sha256'] for s in rows};cache['trace_provenance']=dict(original_cache_sha256=digest(a.cache),sources=sources,added=added,primary_weights_and_projection_verified=True)
    a.output_cache.write_text(json.dumps(cache,indent=2)+'\n');print(json.dumps(dict(added=added,splits=manifest['splits']),indent=2))

if __name__=='__main__':main()
