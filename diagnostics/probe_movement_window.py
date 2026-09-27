"""Offline combat movement counterfactual; keep recorded targets, weapons and other actions."""
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
    directives={key:row['directive'] for key,row in decisions.items()}
    results=[]
    for variant in ('recorded','recomputed','stationary','backward','strafe_left','strafe_right','retained_recorded_facts'):
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
                        if variant=='retained_recorded_facts':
                            from doomlib.compact_movement import movement_facts
                            from training.build_map3_retained_movement import choose_retained
                            packet=decisions[d['decision_id']]['packet']
                            facts=movement_facts(packet['state'],packet['questions']['movement'])
                            d['movement']=choose_retained([dict(distance=facts['nearest'])],facts['clearance'],facts['current'])
                        if accepted_id!=d['decision_id']:
                            executor.accept(d,tick);accepted_id=d['decision_id']
                        computed,_=executor.act(s,tick)
                        buttons[4:6]=computed[4:6]
                        if variant=='retained_recorded_facts':buttons[:4]=computed[:4]
                        if variant=='stationary':buttons[:4]=[0.,0.,0.,0.]
                        if variant=='backward':buttons[:4]=[0.,1.,0.,0.]
                        if variant=='strafe_left':buttons[:4]=[0.,0.,1.,0.]
                        if variant=='strafe_right':buttons[:4]=[0.,0.,0.,1.]
                if variant in ('recorded','recomputed'):
                    if max(abs(s[k]-row[k]) for k in initial)>.01:raise RuntimeError(variant+' baseline state diverged')
                    if max(abs(a-b) for a,b in zip(buttons,row['buttons']))>.00001:raise RuntimeError(variant+' baseline buttons differ')
                history.append(dict(tick=tick,hp=s['hp'],kills=s['kills'],buttons=buttons));game.make_action(buttons,1)
            result=dict(variant=variant,initial=initial,final=values(),dead=game.is_player_dead(),ticks=len(history),fire_ticks=sum(bool(r['buttons'][5]) for r in history),history=history);results.append(result);print({k:v for k,v in result.items() if k!='history'},flush=True)
        finally:game.close()
    output.write_text(json.dumps(dict(note=__doc__+' Retained variant relabels movement using the original request facts; it is not neural inference or an adaptive full-game teacher.',source_run=str(run),start=start,end=end,results=results),indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('run',type=Path);p.add_argument('--start',type=int,required=True);p.add_argument('--end',type=int,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.exists():p.error('Output exists')
    probe(a.run,a.start,a.end,a.output)
