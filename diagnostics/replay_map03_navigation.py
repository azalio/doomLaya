"""Replay exact recorded buttons and inspect connectivity; no new model gameplay."""
import argparse
import copy
import importlib.util
import json
import sys
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import vizdoom
from agent import make_game,BUTTONS
from doomlib.navigation import Navigator


def replay(run,cut,output):
    config=json.loads((run/'config.json').read_text())
    rows=[]
    with (run/'telemetry.jsonl').open() as handle:
        for line in handle:
            row=json.loads(line);rows.append(row)
            if row['tick']>=cut:break
    if rows[-1]['tick']!=cut:raise ValueError('Tick is not recorded')
    spec=importlib.util.spec_from_file_location('recorded_mission',run/'source/doomlib/mission.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    data=module.map_data(Path(vizdoom.__file__).parent/'freedoom2.wad','MAP03')
    doors=data['doors']+[dict(sector=i,key=None) for s in data['switches'] for i in s['sectors']]
    args=config.get('args') or dict(map=config['map'],skill=config['skill'],seed=config['seed'],show=False,sound=False,weapon_sensor=True)
    game=make_game(SimpleNamespace(**args),no_monsters=config.get('no_monsters',False))
    idle=[0.]*len(BUTTONS)
    def observe():
        return {k:float(game.get_game_variable(getattr(vizdoom.GameVariable,v))) for k,v in [('x','POSITION_X'),('y','POSITION_Y'),('z','POSITION_Z'),('angle','ANGLE'),('hp','HEALTH')]}
    try:
        game.make_action(idle,12)
        initial_nav=Navigator(game.get_state().sectors,doors,data['teleports'])
        for row in rows:
            if game.is_episode_finished():
                game.new_episode();game.make_action(idle,12)
                initial_nav=Navigator(game.get_state().sectors,doors,data['teleports'])
            if row['tick']%700==0 or row['tick']==cut:
                current=observe();difference={k:abs(current[k]-row[k]) for k in current}
                if max(difference.values())>.01:raise RuntimeError(f"Replay diverged at {row['tick']}: {difference}")
            if row['tick']==cut:break
            game.make_action(row['buttons'],1)
            if row['tick']%1400==0:print('REPLAY',row['tick'],cut,flush=True)
        raw=game.get_state();state=copy.deepcopy(rows[-1])
        changed=initial_nav.update_floors(raw.sectors)
        fresh=Navigator(raw.sectors,doors,data['teleports'])
        report=dict(note=__doc__,source_run=str(run),tick=cut,episode=state['episode'],position=current,replay_matches=True,changed_floor_sectors=changed,graphs={})
        for name,nav in [('initial_geometry_updated_floors',initial_nav),('rebuilt_geometry',fresh)]:
            nav.observe(state,cut);reachable=nav.reachable((state['x'],state['y']))
            report['graphs'][name]=dict(reachable_cells=len(reachable),exits={e['line']:nav.nearest(e['approach']) in reachable for e in data['exits'] if not e['secret']},exit=nav.nearest(next(e for e in data['exits'] if not e['secret'])['approach']) in reachable,switches={s['id']:nav.nearest(s['approach']) in reachable for s in data['switches']},keys={s['color']:nav.nearest((s['x'],s['y'])) in reachable for s in data['key_markers']})
        output.write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2))
    finally:game.close()


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('run',type=Path);p.add_argument('--tick',type=int,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.exists():p.error('output exists')
    replay(a.run,a.tick,a.output)
