"""Compare model responses with factual lift/key geometry on saved loop states."""
import argparse,collections,copy,json,sys
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from agent import make_game,BUTTONS,LayaClient
from mission import Mission,map_data
from executor import Executor
from policy import request,decode
from decision_questions import factorize,with_commitment,refresh_attack_target,dependencies


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('run',type=Path);p.add_argument('--endpoint',default='http://127.0.0.1:8001/predict');p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.exists():p.error('output exists')
    game=make_game(SimpleNamespace(map='MAP02',skill=3,seed=54,show=False,sound=False),no_monsters=True)
    try:
        game.make_action([0]*len(BUTTONS),12);mission=Mission(map_data(game.get_doom_game_path(),'MAP02'));controller=Executor(game.get_state().sectors,mission,mechanism_facts=True)
        routes={s['id']:s.get('route_keys',[]) for s in mission.data['switches'] if s.get('route_keys')}
    finally:game.close()
    rows=[json.loads(line) for line in (a.run/'telemetry.jsonl').read_text().splitlines()]
    decisions=[json.loads(line) for line in (a.run/'decisions.jsonl').read_text().splitlines()]
    candidates=[d for d in decisions if d['tick']>=800*35 and d['packet']['observation']['execution'].get('action')=='use_switch']
    selected=candidates[-20:]
    client=LayaClient(a.endpoint,'doom-adapted');routing=client.health();results=[]
    try:
        for d in selected:
            state=copy.deepcopy(rows[d['tick']]);state['execution']=d['packet']['observation']['execution']
            for switch in state['switches']:
                if switch['id'] in routes:switch['route_keys']=routes[switch['id']]
            memory={i['id']:i for i in d['packet']['targets']['item'].values()}
            packet=refresh_attack_target(with_commitment(factorize(request(state,memory,mission))));packet['question_dependencies']=dependencies(packet)
            answers={}
            for name,value in [('original',d['packet']),('facts',packet)]:
                response=client.predict(value['state'],value['questions'],value.get('question_dependencies'))
                if response['routing']['weights_sha256']!=routing['weights_sha256']:raise RuntimeError('Checkpoint changed')
                answers[name]=dict(directive=decode(response,value,1),answers=response['answers'],state=value['state'])
            results.append(dict(tick=d['tick'],**answers))
        counts={name:dict(collections.Counter(str(r[name]['directive']['action'])+' '+str((r[name]['directive'].get('target') or {}).get('id')) for r in results)) for name in ('original','facts')}
        report=dict(note='Development counterfactual input probe, not gameplay evidence',routing=routing,geometry_routes=routes,counts=counts,results=results)
        a.output.write_text(json.dumps(report,indent=2));print(json.dumps(dict(geometry_routes=routes,counts=counts),indent=2))
    finally:client.session.close()


if __name__=='__main__':main()
