"""Compare explicit weapons or movements from one exact replayed combat state.

Diagnostic only: replay recorded buttons, save the engine state, then hold the
same recorded enemy for each variant. No model gameplay claim.
"""
import argparse,copy,json,sys,tempfile
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import vizdoom
from agent import BUTTONS,Sensors,make_game
from doomlib.executor import Executor
from doomlib.mission import Mission,map_data


def probe(run,cut,output,movements=None,duration=175,replay_each=False):
    config=json.loads((run/'config.json').read_text())
    decisions={}
    for d in map(json.loads,(run/'decisions.jsonl').read_text().splitlines()):
        decisions[d['directive']['decision_id']]=d
    game=make_game(SimpleNamespace(**config['args']))
    try:
        game.make_action([0.]*len(BUTTONS),12)
        for line in (run/'telemetry.jsonl').open():
            row=json.loads(line)
            if game.is_episode_finished():game.new_episode();game.make_action([0.]*len(BUTTONS),12)
            if row['tick']==cut:break
            game.make_action(row['buttons'],1)
        if row['tick']!=cut:raise ValueError('Tick unavailable')
        current={k:float(game.get_game_variable(getattr(vizdoom.GameVariable,v))) for k,v in [('x','POSITION_X'),('y','POSITION_Y'),('z','POSITION_Z'),('hp','HEALTH')]}
        if max(abs(current[k]-row[k]) for k in current)>.01:raise RuntimeError('Replay diverged')
        directive=copy.deepcopy(decisions[row['execution']['decision_id']]['directive'])
        if directive['action']!='attack':raise ValueError('Choose an attack tick')
        directive.pop('expires_tick',None)
        if not any(e['id']==directive['target']['id'] and e.get('visible',True) for e in row['enemies']):raise ValueError('Choose a tick with the selected enemy visible')
        original_target=next(o for o in game.get_state().objects if o.id==directive['target']['id'])
        original_xyz=(original_target.position_x,original_target.position_y,original_target.position_z)
        output.parent.mkdir(parents=True,exist_ok=True)
        report=dict(note=__doc__,restore_method='full_recorded_buttons' if replay_each else 'engine_save_load',source_run=str(run),tick=cut,position=current,recorded_directive=directive,replay_matches=True,trials=[])
        with tempfile.TemporaryDirectory() as directory:
            save=str(Path(directory)/'combat.zds');game.save(save)
            variants=[dict(weapon=directive['weapon'],movement=m) for m in movements] if movements else [dict(weapon=w) for w in (3,4)]
            for variant in variants:
                if replay_each:
                    game.close();game=make_game(SimpleNamespace(**config['args']))
                    game.make_action([0.]*len(BUTTONS),12)
                    for line in (run/'telemetry.jsonl').open():
                        replayed=json.loads(line)
                        if game.is_episode_finished():game.new_episode();game.make_action([0.]*len(BUTTONS),12)
                        if replayed['tick']==cut:break
                        game.make_action(replayed['buttons'],1)
                    restored={k:float(game.get_game_variable(getattr(vizdoom.GameVariable,v))) for k,v in [('x','POSITION_X'),('y','POSITION_Y'),('z','POSITION_Z'),('hp','HEALTH')]}
                    if restored!=current:raise RuntimeError('Variant replay diverged')
                else:
                    game.new_episode();game.load(save)
                mission=Mission(map_data(game.get_doom_game_path(),'MAP03'))
                executor=Executor(game.get_state().sectors,mission)
                sensors=Sensors(mission.data['door_sectors'],mission.data['doors'],weapon_sensor=True)
                matches=[o for o in game.get_state().objects if o.name==original_target.name and max(abs(a-b) for a,b in zip((o.position_x,o.position_y,o.position_z),original_xyz))<.01]
                if len(matches)!=1:raise ValueError('Saved target failed exact identity match: '+str(dict(name=original_target.name,xyz=original_xyz,candidates=[dict(name=o.name,xyz=[o.position_x,o.position_y,o.position_z]) for o in game.get_state().objects if abs(o.position_x-original_xyz[0])+abs(o.position_y-original_xyz[1])<64])))
                loaded_target=matches[0]
                target=dict(directive['target'],id=loaded_target.id)
                command=dict(directive,**variant);command['target']=target;executor.accept(command,0)
                history=[];dead=False;removed_tick=None
                for tick in range(duration):
                    if game.is_episode_finished():dead=game.is_player_dead();break
                    raw,s=sensors.read(game,tick)
                    mission.observe(s,raw.sectors);executor.observe(s,tick,raw.sectors)
                    objects={o.id for o in raw.objects if o.name==original_target.name}
                    if target['id'] not in objects or target['id'] in s['dead_ids']:
                        removed_tick=tick;break
                    buttons,refs=executor.act(s,tick)
                    history.append(dict(tick=tick,hp=s['hp'],weapon=s['weapon'],ammo=s['ammo'],kills=s['kills'],buttons=buttons,target_visible=any(e['id']==target['id'] and e.get('visible',True) for e in s['enemies'])))
                    game.make_action(buttons,1)
                trial=dict(variant,dead=dead,target_removed_tick=removed_tick,final_hp=float(game.get_game_variable(vizdoom.GameVariable.HEALTH)),history=history)
                report['trials'].append(trial)
                print('TRIAL', {k:v for k,v in trial.items() if k!='history'},flush=True)
        output.write_text(json.dumps(report,indent=2));print(json.dumps({**report,'trials':[{k:v for k,v in t.items() if k!='history'} for t in report['trials']]},indent=2))
    finally:game.close()


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('run',type=Path);p.add_argument('--tick',type=int,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--movements',nargs='+',choices=['stationary','backward','strafe_left','strafe_right']);p.add_argument('--ticks',type=int,default=175);p.add_argument('--replay-each',action='store_true',help='Replay original buttons separately for every variant, avoiding save/load state advancement');a=p.parse_args()
    if a.output.exists():p.error('Output exists')
    if not 1<=a.ticks<=175:p.error('--ticks must be in 1..175')
    probe(a.run,a.tick,a.output,a.movements,a.ticks,a.replay_each)
