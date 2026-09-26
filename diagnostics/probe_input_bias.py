"""Measure goal, option-order, and object-ID sensitivity on frozen requests."""
import argparse
import collections
import copy
import hashlib
import json
import re
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from agent import LayaClient


def variant(row,name):
    state=row['state'];question=copy.deepcopy(row['question']);mapping={}
    if name in ('resource_facts','resource_reverse','resource_anonymous_ids','resource_task_state'):
        from training.resource_augmentation import resource_facts
        question=resource_facts(row)['question']
    if name in ('task_state','resource_task_state') and row['kind']!='command':
        prefixes={
            'weapon':('HP ','Inventory:','Enemies:','No enemies'),
            'item':('HP ','Inventory:','Collected keys:'),
            'switch':('Current command: use_switch','Available mechanisms:','Collected keys:'),
            'movement':('Enemy range:','Inventory:','Clearance:','Enemies:','No enemies'),
            'enemy':('Enemies:','No enemies'),
            'combat':('Enemies:','No enemies'),
        }[row['kind']]
        state='\n'.join(line for line in state.splitlines() if line.startswith(prefixes))
        if not state:raise ValueError('Scoped state is empty: '+row['kind'])
    if name=='no_goal':
        state='\n'.join(v for v in state.splitlines() if not v.startswith('Current command:'))
    if name in ('reverse','resource_reverse'):question['criteria']=dict(reversed(list(question['criteria'].items())))
    if name in ('anonymous_ids','resource_anonymous_ids'):
        ids=list(dict.fromkeys(re.findall(r'#([A-Za-z0-9_]+)',state)))
        if row['kind'] in ('item','enemy','switch','combat'):
            ids+=list(k for k in question['criteria'] if k not in ids and k!='hold')
        mapping={oid:'object'+chr(65+i) for i,oid in enumerate(ids)}
        def replace(text):return re.sub(r'#([A-Za-z0-9_]+)',lambda m:'#'+mapping.get(m[1],m[1]),text)
        state=replace(state)
        question['criteria']={mapping.get(k,k):replace(v) for k,v in question['criteria'].items()}
    return state,question,{v:k for k,v in mapping.items()}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('challenge',type=Path);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--explicit-movement',action='store_true')
    p.add_argument('--variants',nargs='+',choices=['original','no_goal','reverse','anonymous_ids','resource_facts','resource_reverse','resource_anonymous_ids','task_state','resource_task_state'],default=['original','no_goal','reverse','anonymous_ids'])
    a=p.parse_args()
    if a.output.exists():p.error('output exists')
    rows=json.loads(a.challenge.read_text())
    if a.explicit_movement:
        from movement_questions import explicit_example
        rows=[explicit_example(r) for r in rows]
    client=LayaClient('http://127.0.0.1:8001/predict','doom-adapted');routing=client.health();results=[]
    try:
        for i,row in enumerate(rows):
            answers={}
            for name in a.variants:
                state,q,reverse=variant(row,name);result=client.predict(state,{row['kind']:q})
                if result['routing']['weights_sha256']!=routing['weights_sha256']:raise RuntimeError('Checkpoint changed')
                answer=result['answers'][row['kind']];choice=reverse.get(answer['choice'],answer['choice'])
                answers[name]=dict(choice=choice,correct=choice==row['label'],probabilities=answer['probabilities'])
            results.append(dict(index=i,kind=row['kind'],case=row['case'],expected=row['label'],source_tick=row['source_tick'],answers=answers))
            if i%10==0:print('PROBE',i+1,len(rows),flush=True)
    finally:client.session.close()
    scores={name:dict(correct=sum(r['answers'][name]['correct'] for r in results),changed=sum(r['answers'][name]['choice']!=r['answers'][a.variants[0]]['choice'] for r in results),by_kind={k:dict(correct=sum(r['answers'][name]['correct'] for r in results if r['kind']==k),total=sum(r['kind']==k for r in results)) for k in sorted({r['kind'] for r in results})}) for name in a.variants}
    report=dict(note='Input ablations on frozen development questions, not gameplay or independent accuracy.',challenge=str(a.challenge),challenge_sha256=hashlib.sha256(a.challenge.read_bytes()).hexdigest(),routing=routing,explicit_movement=a.explicit_movement,cases=len(rows),scores=scores,results=results)
    a.output.write_text(json.dumps(report,indent=2));print(json.dumps(scores,indent=2))


if __name__=='__main__':main()
