"""Mechanical exit-line fixture: modified spawn, no monsters and no model decisions."""
import argparse,json,sys
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import vizdoom
from agent import make_game,BUTTONS,Sensors
from doomlib.mission import Mission,map_data
from doomlib.executor import Executor
from diagnostics.probe_map03_floor import run_fixture


def probe(output):
    output.mkdir();run_fixture(output/'floor-fixture');wad=output/'floor-fixture'/'fixture.wad';results=[]
    for line,press_floor in ((1669,False),(1670,False),(1669,True)):
        game=make_game(SimpleNamespace(map='MAP03',skill=3,seed=54,show=False,sound=False),no_monsters=True)
        game.close();game.set_doom_game_path(str(wad.resolve()));game.init();history=[]
        try:
            game.make_action([0.]*len(BUTTONS),12)
            mission=Mission(map_data(wad,'MAP03'));mission.exit=next(e for e in mission.data['exits'] if e['line']==line)
            sensors=Sensors(mission.data['door_sectors'],mission.data['doors']);controller=Executor(game.get_state().sectors,mission)
            for tick in range(700):
                if game.is_episode_finished():break
                raw,state=sensors.read(game,tick);mission.observe(state,raw.sectors);controller.observe(state,tick,raw.sectors)
                switch=next(s for s in state['switches'] if s['id']==2839)
                action='use_switch' if press_floor and not switch['activated'] else 'exit'
                if tick%18==0:controller.accept(dict(action=action,target=dict(switch) if action=='use_switch' else None,weapon=None,decision_id=tick+1,command=action,expires_tick=tick+70),tick)
                buttons,refs=controller.act(state,tick)
                history.append(dict(tick=tick,x=state['x'],y=state['y'],z=state['z'],floor_height=raw.sectors[306].floor_height,execution=state['execution'],buttons=buttons))
                game.make_action(buttons,1)
            row=dict(exit_line=line,press_floor=press_floor,episode_finished=game.is_episode_finished(),dead=game.is_player_dead(),ticks=len(history),final=history[-1],history=history);results.append(row);print({k:v for k,v in row.items() if k not in ('history','final')},flush=True)
        finally:game.close()
    (output/'result.json').write_text(json.dumps(dict(note=__doc__,results=results),indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.exists():p.error('Output exists')
    probe(a.output)
