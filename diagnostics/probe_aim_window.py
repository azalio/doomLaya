"""Offline aiming-rate counterfactual; all buttons except selected-target aim/fire stay recorded."""
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
    directives={r['directive']['decision_id']:r['directive'] for r in map(json.loads,(run/'decisions.jsonl').read_text().splitlines())}
    original=directives[window[0]['execution']['decision_id']]
    if original['action']!='attack':raise ValueError('Start with an explicit attack')
    results=[]
    for variant in ('recorded',9,18,36):
        game=make_game(SimpleNamespace(**config));sensors=Sensors(weapon_sensor=True);history=[];target_removed=None
        def values():return {k:float(game.get_game_variable(getattr(vizdoom.GameVariable,v))) for k,v in [('x','POSITION_X'),('y','POSITION_Y'),('z','POSITION_Z'),('hp','HEALTH'),('kills','KILLCOUNT')]}
        try:
            game.make_action([0.]*len(BUTTONS),12)
            for row in rows:
                if row['tick']>=start:break
                if game.is_episode_finished():game.new_episode();game.make_action([0.]*len(BUTTONS),12);sensors=Sensors(weapon_sensor=True)
                if row['tick']>=start-70:sensors.read(game,row['tick'])
                game.make_action(row['buttons'],1)
            initial=values()
            if max(abs(initial[k]-window[0][k]) for k in initial)>.01:raise RuntimeError('Prefix mismatch')
            executor=Executor(game.get_state().sectors)
            for row in window:
                if game.is_episode_finished():break
                tick=row['tick'];raw,s=sensors.read(game,tick);buttons=list(row['buttons'])
                if variant=='recorded':
                    if max(abs(s[k]-row[k]) for k in initial)>.01:raise RuntimeError('Recorded baseline diverged')
                else:
                    d=copy.deepcopy(directives[row['execution']['decision_id']])
                    if d['action']=='attack':
                        executor.accept(d,tick);computed,_=executor.act(s,tick)
                        buttons[4:6]=computed[4:6]
                        current=next((e for e in s['enemies'] if e['id']==d['target']['id']),None)
                        if current:
                            bearing=current.get('aim_bearing',current['bearing'])
                            buttons[4]=max(-variant,min(variant,bearing))
                    if variant==9:
                        if max(abs(s[k]-row[k]) for k in initial)>.01:raise RuntimeError('Recomputed 9-degree baseline diverged')
                        if max(abs(a-b) for a,b in zip(buttons,row['buttons']))>.00001:raise RuntimeError('Recomputed baseline buttons differ')
                history.append(dict(tick=tick,hp=s['hp'],kills=s['kills'],target_visible=any(e['id']==original['target']['id'] and e.get('visible',True) for e in s['enemies']),buttons=buttons));game.make_action(buttons,1)
            result=dict(variant=variant,initial=initial,final=values(),dead=game.is_player_dead(),ticks=len(history),first_target_removed=target_removed,fire_ticks=sum(bool(r['buttons'][5]) for r in history),history=history);results.append(result);print({k:v for k,v in result.items() if k!='history'},flush=True)
        finally:game.close()
    output.write_text(json.dumps(dict(note=__doc__,source_run=str(run),start=start,end=end,first_target=original['target'],results=results),indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('run',type=Path);p.add_argument('--start',type=int,required=True);p.add_argument('--end',type=int,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.exists():p.error('Output exists')
    probe(a.run,a.start,a.end,a.output)
