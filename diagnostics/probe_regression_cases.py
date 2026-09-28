"""Replay saved regression cases through the real model API, without gameplay."""
import argparse
import hashlib
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))


def check(case,answers):
    if case['check']=='expected_enemy_first':
        return case['packet']['enemy_sequences'][answers['enemy']['choice']][0]==case['expected_enemy']
    if case['check']=='visible_enemy_first':
        first=case['packet']['enemy_sequences'][answers['enemy']['choice']][0]
        return first in case['expected_visible_targets']
    for kind in ('movement','switch','weapon'):
        if case['check']=='expected_'+kind:
            return answers[kind]['choice']==case['expected_'+kind]
    command=answers['command']['choice']
    item=answers.get('item',{}).get('choice')
    if case['check']=='expected_command':
        return command==case['expected_command']
    if case['check']=='avoid_full_health_medikit':
        return command!='pickup' or case['packet']['targets']['item'][item]['name'] not in ('Medikit','Stimpack')
    if case['check'] in ('collect_missing_yellow_key','collect_missing_key','expected_pickup_item'):
        return command=='pickup' and item==case['expected_item']
    raise ValueError('Unknown regression assertion')


def main():
    from agent import LayaClient
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--cases',type=Path,default=Path('fixtures/v031-regression-cases.json'))
    p.add_argument('--endpoint',default='http://127.0.0.1:8002/predict')
    p.add_argument('--output',type=Path,required=True)
    p.add_argument('--expect-head',action='append',default=[],metavar='KIND=CHECKPOINT',help='Require this local checkpoint hash in the API head manifest')
    a=p.parse_args()
    if a.output.exists():p.error('Output exists')
    cases=json.loads(a.cases.read_text())['cases']
    if not cases:raise ValueError('Empty regression cases')
    client=LayaClient(a.endpoint,'doom-adapted');health=client.health();results=[]
    for spec in a.expect_head:
        kind,sep,path=spec.partition('=')
        if not sep or not path:raise ValueError('Expected KIND=CHECKPOINT')
        with (Path(path)/'model.safetensors').open('rb') as handle:
            expected=hashlib.file_digest(handle,'sha256').hexdigest()
        if health.get('question_heads',{}).get(kind,{}).get('weights_sha256')!=expected:
            raise ValueError('API checkpoint differs from expected '+kind+' head')
        auxiliary=json.loads((Path(path)/'rl_agent_config.json').read_text()).get('doom_adaptation',{}).get('numeric_residual')
        if auxiliary:
            for filename,metadata_key,config_key in [('numeric-residual.json','numeric_residual_spec_sha256','spec_sha256'),('numeric-residual.safetensors','numeric_residual_weights_sha256','weights_sha256')]:
                actual=hashlib.sha256((Path(path)/filename).read_bytes()).hexdigest()
                if actual!=auxiliary[config_key] or health['question_heads'][kind].get(metadata_key)!=actual:
                    raise ValueError('API numeric residual differs: '+filename)
    try:
        for case in cases:
            packet=case['packet'];kinds=(case['check'].removeprefix('expected_'),) if case['check'] in ('expected_movement','expected_switch','expected_weapon') else ('command','item')
            if case['check'] in ('visible_enemy_first','expected_enemy_first'):kinds=('enemy',)
            questions={k:q for k,q in packet['questions'].items() if k in kinds}
            response=client.predict(packet['state'],questions)
            if response['routing']['weights_sha256']!=health['weights_sha256']:raise ValueError('Checkpoint changed during replay')
            passed=check(case,response['answers'])
            results.append(dict(source_run=case['source_run'],tick=case['tick'],check=case['check'],passed=passed,answers=response['answers']))
    finally:client.session.close()
    passed=all(row['passed'] for row in results)
    a.output.write_text(json.dumps(dict(note='Development regression replay; source failures contributed training data. Passing is not independent validation or gameplay completion.',passed=passed,routing=health,results=results),indent=2)+'\n')
    print(json.dumps(dict(passed=passed,correct=sum(r['passed'] for r in results),total=len(results))))
    return 0 if passed else 1


if __name__=='__main__':raise SystemExit(main())
