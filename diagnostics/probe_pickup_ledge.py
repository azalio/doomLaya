"""Engine pickup fixture with a modified spawn and a stale route, not model gameplay."""
import argparse,importlib.util,json,math,sys
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from agent import make_game,BUTTONS,Sensors
from mission import Mission,map_data
from executor import Executor
from diagnostics.probe_door_corner import spawn_fixture


def load_source(path,name):
    spec=importlib.util.spec_from_file_location(name,path);module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module);return module


def run_fixture(output,baseline_source=None):
    output=Path(output);fixture=spawn_fixture(output,(822,-430,272))
    game=make_game(SimpleNamespace(map='MAP02',skill=3,seed=54,show=False,sound=False),no_monsters=True)
    game.close();game.set_doom_game_path(str(fixture.resolve()));game.init()
    history=[];collected=None
    try:
        game.make_action([0]*len(BUTTONS),12)
        mission=Mission(map_data(game.get_doom_game_path(),'MAP02'))
        sensors=Sensors(mission.data['door_sectors'],mission.data['doors'])
        controller=Executor(game.get_state().sectors,mission)
        if baseline_source:
            old_nav=load_source(Path(baseline_source)/'navigation.py','baseline_navigation')
            old_exec=load_source(Path(baseline_source)/'executor.py','baseline_executor')
            old_exec.Navigator=old_nav.Navigator
            controller=old_exec.Executor(game.get_state().sectors,mission)
        actual=next(o for o in game.get_state().objects if o.name=='HealthBonus' and abs(o.position_x-816)<1 and abs(o.position_y+496)<1)
        item=dict(id=actual.id,name='HealthBonus',category='Health',x=816.,y=-496.,z=actual.position_z,distance=2.1)
        controller.known[item['id']]=dict(item)
        initial_present=False
        for tick in range(1050):
            raw,state=sensors.read(game,tick);mission.observe(state,raw.sectors);controller.observe(state,tick,raw.sectors)
            present=any(o.name=='HealthBonus' and abs(o.position_x-816)<1 and abs(o.position_y+496)<1 for o in raw.objects)
            if tick==0:
                initial_present=present
                goal=controller.navigator.nearest((816,-496))
                controller.navigator.requested=('point',goal);controller.navigator.path=[goal]
            if tick%18==0:
                controller.accept(dict(action='pickup',target=dict(item),weapon=None,decision_id=tick+1,command='pickup',expires_tick=tick+70),tick)
            buttons,refs=controller.act(state,tick)
            history.append(dict(tick=tick,position=[state['x'],state['y'],state['z']],hp=state['hp'],execution=state['execution'],buttons=buttons,refs=refs,present=present))
            if initial_present and not present and math.dist((state['x'],state['y']),(816,-496))<48:
                collected=tick;break
            game.make_action(buttons,1)
    finally:game.close()
    result=dict(note='Mechanics fixture with modified spawn, remembered target and no monsters; not Laya gameplay',baseline_source=str(baseline_source) if baseline_source else None,initial_present=initial_present,collected_tick=collected,history=history)
    (output/'result.json').write_text(json.dumps(result,indent=2));return result


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--baseline-source',type=Path);a=p.parse_args()
    if a.output.exists():p.error('output already exists')
    result=run_fixture(a.output,a.baseline_source);print(json.dumps({k:v for k,v in result.items() if k!='history'},indent=2));raise SystemExit(result['collected_tick'] is None)
