"""Replay recorded buttons, then isolate aiming at one preselected enemy."""
import argparse
import json
import math
import sys
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import vizdoom as vzd
from PIL import Image
from agent import BUTTONS,Sensors,make_game,bearing,wrap


def trial(args,rows,output,cut,vertical):
    game=vzd.DoomGame()
    game.set_doom_game_path(str(Path(vzd.__file__).parent/'freedoom2.wad'))
    if args['weapon_sensor']:game.set_doom_scenario_path(str(Path('assets/weapon_sensor.pk3').resolve()))
    game.set_doom_map(args['map']);game.set_doom_skill(args['skill']);game.set_seed(args['seed']);game.set_mode(vzd.Mode.PLAYER)
    game.set_screen_resolution(vzd.ScreenResolution.RES_640X480);game.set_screen_format(vzd.ScreenFormat.RGB24)
    game.set_depth_buffer_enabled(True);game.set_labels_buffer_enabled(True);game.set_sectors_info_enabled(True);game.set_objects_info_enabled(True)
    game.set_window_visible(False);game.set_sound_enabled(False);game.set_render_hud(True)
    game.set_available_buttons(BUTTONS+[vzd.Button.LOOK_UP_DOWN_DELTA]);game.set_episode_timeout(0)
    game.add_game_args('+freelook 1 +sv_cheats 1 +neverswitchonpickup 1');game.init()
    sensors=Sensors(weapon_sensor=args['weapon_sensor']);idle=[0.]*15
    def var(name):return float(game.get_game_variable(getattr(vzd.GameVariable,name)))
    history=[]
    try:
        game.make_action(idle,12)
        for i,row in enumerate(rows[:cut]):
            if game.is_episode_finished():raise RuntimeError('Replay episode ended at tick '+str(i))
            _,observed=sensors.read(game,i)
            if i%35==0:
                errors={k:abs(observed[k]-row[k]) for k in ('x','y','z','hp','angle')}
                if max(errors.values())>.01:raise RuntimeError('First replay divergence at '+str(i)+': '+str(errors))
            game.make_action(row['buttons']+[0.],1)
            if i%1400==0:print('REPLAY',vertical,i,cut,flush=True)
        raw,s=sensors.read(game,cut);expected=rows[cut]
        differences={k:abs(s[k]-expected[k]) for k in ('x','y','z','hp','angle')}
        if max(differences.values())>.01:
            report=dict(vertical=vertical,replay_matches=False,differences=differences,actual={k:s[k] for k in differences},expected={k:expected[k] for k in differences})
            (output/f"{'vertical' if vertical else 'horizontal'}-mismatch.json").write_text(json.dumps(report,indent=2))
            raise RuntimeError('Recorded trajectory did not replay: '+str(report))
        target_id=expected['execution']['target_id'];target=next(e for e in s['enemies'] if e['id']==target_id)
        initial=dict(position=[s['x'],s['y'],s['z']],camera_z=var('CAMERA_POSITION_Z'),target=target,weapon=s['weapon'],ammo=s['ammo'],differences=differences)
        game.send_game_command('god');game.send_game_command('freeze');game.make_action(idle,1)
        initial_kills=var('KILLCOUNT');first_visible=kill_tick=None
        for tick in range(140):
            raw,s=sensors.read(game,cut+1+tick)
            current=next((e for e in s['enemies'] if e['id']==target_id),None)
            if current:target=current
            visible=bool(current and current.get('visible',True))
            yaw=target.get('aim_bearing',target['bearing']) if visible else bearing(target['x'],target['y'],s['x'],s['y'],s['angle'])
            distance=math.hypot(target['x']-s['x'],target['y']-s['y'])
            desired=math.degrees(math.atan2(var('CAMERA_POSITION_Z')-(target['z']+28),distance));pitch=wrap(var('PITCH'));error=wrap(desired-pitch)
            buttons=list(idle);buttons[4]=max(-9,min(9,yaw))
            if vertical:buttons[-1]=max(-9,min(9,-error))
            buttons[5]=float(visible and abs(yaw)<5 and (not vertical or abs(error)<5))
            if visible and first_visible is None:first_visible=tick
            kills=int(var('KILLCOUNT')-initial_kills)
            history.append(dict(tick=tick,visible=visible,pitch=pitch,desired_pitch=desired,position=[s['x'],s['y'],s['z']],target=target,ammo=s['ammo'],kills=kills,buttons=buttons))
            if tick in (0,20,139) or kills:Image.fromarray(raw.screen_buffer).save(output/f"{'vertical' if vertical else 'horizontal'}-{tick}.png")
            if kills:kill_tick=tick;break
            game.make_action(buttons,1)
        return dict(vertical=vertical,replay_matches=True,initial=initial,first_visible_tick=first_visible,kill_tick=kill_tick,final=history[-1],history=history)
    finally:game.close()


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('run',type=Path);p.add_argument('--tick',type=int,default=6300);p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.output.mkdir(exist_ok=False)
    config=json.loads((a.run/'config.json').read_text());rows=[]
    for line in (a.run/'telemetry.jsonl').open():
        rows.append(json.loads(line))
        if rows[-1]['tick']>=a.tick:break
    assert all(r['episode']==0 for r in rows)
    results=[trial(config['args'],rows,a.output,a.tick,v) for v in (False,True)]
    report=dict(note='Recorded actions reproduce the source position and health before intervention. Afterwards god mode and frozen enemies isolate aim only. This is not model gameplay.',source_run=str(a.run),source_tick=a.tick,results=results)
    (a.output/'result.json').write_text(json.dumps(report,indent=2));print(json.dumps({**report,'results':[{k:v for k,v in r.items() if k!='history'} for r in results]},indent=2))


if __name__=='__main__':main()
