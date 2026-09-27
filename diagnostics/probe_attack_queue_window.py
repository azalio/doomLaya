"""Offline attack-queue counterfactual; queue only enemies observed in each recorded request. Never used by the live agent."""
import argparse,copy,json,sys
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import vizdoom
from agent import BUTTONS,Sensors,make_game
from doomlib.executor import Executor


def probe(run,start,end,output):
    config=json.loads((run/'config.json').read_text())['args']
    rows=[]
    for line in (run/'telemetry.jsonl').open():
        r=json.loads(line)
        if r['tick']>=end:break
        rows.append(r)
    window=[r for r in rows if r['tick']>=start]
    if len(window)!=end-start or len({r['episode'] for r in window})!=1:raise ValueError('Incomplete window or episode boundary')
    decisions={r['directive']['decision_id']:r for r in map(json.loads,(run/'decisions.jsonl').read_text().splitlines())}
    directives={k:r['directive'] for k,r in decisions.items()}
    queues={}
    for k,r in decisions.items():
        d=r['directive']
        if d['action']!='attack':continue
        enemies=r['packet'].get('targets',{}).get('enemy',{})
        first=str(d['target']['id'])
        rest=sorted((key for key in enemies if key!=first),key=lambda key:enemies[key]['distance']*(.65 if enemies[key]['name'] in ('ShotgunGuy','Zombieman','ChaingunGuy') else 1))
        queues[k]=[d['target']]+[enemies[key] for key in rest]
    results=[]
    for variant in ('recorded','recomputed','queue','explicit_sequence'):
        game=make_game(SimpleNamespace(**config));sensors=Sensors(weapon_sensor=True);history=[]
        def values():return {k:float(game.get_game_variable(getattr(vizdoom.GameVariable,v))) for k,v in [('x','POSITION_X'),('y','POSITION_Y'),('z','POSITION_Z'),('hp','HEALTH'),('kills','KILLCOUNT')]}
        try:
            game.make_action([0.]*len(BUTTONS),12)
            for row in rows:
                if row['tick']>=start:break
                if game.is_episode_finished():game.new_episode();game.make_action([0.]*len(BUTTONS),12);sensors=Sensors(weapon_sensor=True)
                if row['tick']>=start-70:sensors.read(game,row['tick'])
                game.set_action(row['buttons'])
                game.advance_action(1,row['tick']>=start-71)
            initial=values()
            if max(abs(initial[k]-window[0][k]) for k in initial)>.01:raise RuntimeError('Prefix mismatch')
            executor=Executor(game.get_state().sectors,attack_turn_rate=config.get('attack_turn_rate',9));accepted_id=None
            for row in window:
                if game.is_episode_finished():break
                tick=row['tick'];raw,s=sensors.read(game,tick);buttons=list(row['buttons'])
                if variant!='recorded':
                    d=copy.deepcopy(directives[row['execution']['decision_id']])
                    if d['action']=='attack':
                        if variant=='queue':
                            observed={e['id'] for e in s['enemies']}
                            available=[e for e in queues[d['decision_id']] if e['id'] in observed]
                            if available:d['target']=copy.deepcopy(available[0])
                        if variant=='explicit_sequence':
                            from doomlib.enemy_sequences import with_enemy_sequences
                            from doomlib.decision_questions import decode
                            record=decisions[d['decision_id']];packet=with_enemy_sequences(record['packet']);order=[str(t['id']) for t in queues[d['decision_id']]]
                            key=next(k for k,v in packet['enemy_sequences'].items() if v==order)
                            result=copy.deepcopy(record);result['answers']['enemy']['choice']=key
                            d=decode(result,packet,d['decision_id']);d['expires_tick']=record['directive']['expires_tick']
                        if variant!='explicit_sequence' or accepted_id!=d['decision_id']:
                            executor.accept(d,tick);accepted_id=d['decision_id']
                        computed,_=executor.act(s,tick)
                        buttons[4:6]=computed[4:6]
                if variant in ('recorded','recomputed'):
                    if max(abs(s[k]-row[k]) for k in initial)>.01:raise RuntimeError(variant+' baseline state diverged')
                    if max(abs(a-b) for a,b in zip(buttons,row['buttons']))>.00001:raise RuntimeError(variant+' baseline buttons differ')
                history.append(dict(tick=tick,hp=s['hp'],kills=s['kills'],buttons=buttons));game.make_action(buttons,1)
            result=dict(variant=variant,initial=initial,final=values(),dead=game.is_player_dead(),ticks=len(history),fire_ticks=sum(bool(r['buttons'][5]) for r in history),history=history);results.append(result);print({k:v for k,v in result.items() if k!='history'},flush=True)
        finally:game.close()
    output.write_text(json.dumps(dict(note=__doc__+' The explicit_sequence variant uses the production decoder/executor but a manually selected offline order, not model inference.',source_run=str(run),start=start,end=end,results=results),indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('run',type=Path);p.add_argument('--start',type=int,required=True);p.add_argument('--end',type=int,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.exists():p.error('Output exists')
    probe(a.run,a.start,a.end,a.output)
