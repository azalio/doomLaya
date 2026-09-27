"""Offline weapon counterfactual over a recorded encounter, never live model play.

The baseline replays the original buttons exactly. Alternative branches retain
recorded action, enemy, and movement choices, but hold one weapon. Movement and use
buttons stay recorded; aiming/firing at each recorded enemy use Executor and
current visibility. Each branch replays the complete prefix in a fresh engine.
"""
import argparse,copy,json,sys
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import vizdoom
from agent import BUTTONS,Sensors,make_game
from doomlib.executor import Executor
from doomlib.combat import WEAPON_SLOTS


def probe(run,start,end,output):
    config=json.loads((run/'config.json').read_text())['args']
    rows=[]
    for line in (run/'telemetry.jsonl').open():
        row=json.loads(line)
        if row['tick']>=end:break
        rows.append(row)
    window=[r for r in rows if r['tick']>=start]
    if not window or len(window)!=end-start:raise ValueError('Incomplete window')
    if len({r['episode'] for r in window})!=1:raise ValueError('Window crosses episodes')
    directives={d['directive']['decision_id']:d['directive'] for d in map(json.loads,(run/'decisions.jsonl').read_text().splitlines()) if 'directive' in d}
    results=[]
    for variant,weapon in (("recorded",None),("recomputed",None),("shotgun",3),("rocket_launcher",5)):
        game=make_game(SimpleNamespace(**config));sensors=Sensors(weapon_sensor=True);history=[];last_selection=-1000
        def values():return {k:float(game.get_game_variable(getattr(vizdoom.GameVariable,v))) for k,v in [('x','POSITION_X'),('y','POSITION_Y'),('z','POSITION_Z'),('hp','HEALTH'),('kills','KILLCOUNT'),('weapon','SELECTED_WEAPON')]}
        try:
            game.make_action([0.]*len(BUTTONS),12)
            for row in rows:
                if row['tick']>=start:break
                if game.is_episode_finished():game.new_episode();game.make_action([0.]*len(BUTTONS),12);sensors=Sensors(weapon_sensor=True)
                if row['tick']>=start-70:sensors.read(game,row['tick'])
                game.set_action(row['buttons']);game.advance_action(1,row['tick']>=start-71)
            initial=values()
            if max(abs(initial[k]-window[0][k]) for k in ('x','y','z','hp','kills'))>.01:raise RuntimeError('Prefix mismatch')
            executor=Executor(game.get_state().sectors,attack_turn_rate=config.get('attack_turn_rate',9));accepted_id=None
            for row in window:
                if game.is_episode_finished():break
                tick=row['tick'];raw,s=sensors.read(game,tick);buttons=list(row['buttons'])
                if variant!='recorded':
                    directive=copy.deepcopy(directives[row['execution']['decision_id']])
                    if weapon is not None:directive['weapon']=weapon
                    if directive['action']!='attack':raise ValueError('Weapon probe window must contain only attacks')
                    if accepted_id!=directive['decision_id']:
                        executor.accept(directive,tick);accepted_id=directive['decision_id']
                    computed,_=executor.act(s,tick)
                    buttons[4:6]=computed[4:6];buttons[7:]=computed[7:]
                if variant in ('recorded','recomputed'):
                    if max(abs(s[k]-row[k]) for k in ('x','y','z','hp','kills'))>.01:raise RuntimeError(variant+' baseline state diverged')
                    if max(abs(a-b) for a,b in zip(buttons,row['buttons']))>.00001:raise RuntimeError(variant+' baseline buttons differ')
                history.append(dict(tick=tick,hp=s['hp'],kills=s['kills'],weapon=s['weapon'],buttons=buttons));game.make_action(buttons,1)
            result=dict(variant=variant,weapon=weapon,initial=initial,final=values(),dead=game.is_player_dead(),ticks=len(history),fire_ticks=sum(bool(r["buttons"][5]) for r in history),history=history);results.append(result)
            print({k:v for k,v in result.items() if k!='history'},flush=True)
        finally:game.close()
    output.write_text(json.dumps(dict(note=__doc__,source_run=str(run),start=start,end=end,results=results),indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('run',type=Path);p.add_argument('--start',type=int,required=True);p.add_argument('--end',type=int,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.exists():p.error('Output exists')
    probe(a.run,a.start,a.end,a.output)
