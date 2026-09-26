"""Compare movement choices with measured body clearance on recorded states."""
import argparse
import copy
import json
import re
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from agent import LayaClient


def variant(row,name):
    state=row['state'];q=copy.deepcopy(row['question']);clearance=row['clearance']
    if name=='physical_state':
        space=', '.join(side+' '+('tight' if clearance[side]<6 else 'open') for side in ('left','right','back'))
        state=re.sub(r'space: [^\n]+','space: '+space+'.',state)
        body='Body clearance: '+', '.join(f'{side} {value:.1f}m' for side,value in clearance.items())+'.'
        lines=state.splitlines();position=next(i for i,line in enumerate(lines) if line.startswith('HP '));lines.insert(position,body);state='\n'.join(lines)
    if name=='question_facts':
        from doomlib.movement_questions import describe_movement
        current=re.search(r'Movement: ([^.]+)',state)
        q=describe_movement(q,clearance,current[1] if current else None)
    return state,q


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('fixture',type=Path);p.add_argument('--output',type=Path,required=True);p.add_argument('--require-clearance',action='store_true');p.add_argument('--explicit-movement',action='store_true');a=p.parse_args()
    if a.output.exists():p.error('output exists')
    rows=json.loads(a.fixture.read_text())['cases'];client=LayaClient('http://127.0.0.1:8001/predict','doom-adapted');routing=client.health();results=[]
    try:
        for row in rows:
            answers={}
            for name in ('original','physical_state','question_facts'):
                state,q=variant(row,name)
                if a.explicit_movement:q['criteria'].pop('continue',None)
                r=client.predict(state,{'movement':q});choice=r['answers']['movement']['choice']
                if r['routing']['weights_sha256']!=routing['weights_sha256']:raise RuntimeError('Checkpoint changed')
                current=re.search(r'Movement: ([^.]+)',row['state'])
                movement=current[1] if choice=='continue' and current else choice
                side={'strafe_left':'left','strafe_right':'right','backward':'back'}.get(movement)
                free=row['clearance'].get(side,0)
                answers[name]=dict(choice=choice,movement=movement,clearance=free,has_escape_space=free>=1.5,probabilities=r['answers']['movement']['probabilities'])
            results.append(dict(tick=row['tick'],answers=answers))
    finally:client.session.close()
    counts={name:sum(r['answers'][name]['has_escape_space'] for r in results) for name in ('original','physical_state','question_facts')}
    report=dict(note='Development input ablation, not live gameplay. Geometry comes from the fixture; criterion is at least 1.5m of measured space in the selected direction.',routing=routing,explicit_movement=a.explicit_movement,cases=len(rows),has_escape_space=counts,results=results)
    a.output.write_text(json.dumps(report,indent=2));print(json.dumps(dict(cases=len(rows),has_escape_space=counts),indent=2))
    if a.require_clearance and counts['question_facts']!=len(rows):raise SystemExit(1)


if __name__=='__main__':main()
