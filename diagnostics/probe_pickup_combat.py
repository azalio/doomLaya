"""Mechanical fixture: execute two explicit targets on the unmodified MAP02 start."""
import argparse,copy,json,sys
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from agent import make_game,Sensors,BUTTONS
from executor import Executor
from mission import Mission,map_data


def probe(seed,hold=False):
    args=SimpleNamespace(map='MAP02',skill=3,seed=seed,show=False,sound=False,weapon_sensor=True)
    game=make_game(args)
    try:
        game.make_action([0]*len(BUTTONS),12)
        mission=Mission(map_data(game.get_doom_game_path(),'MAP02'))
        controller=Executor(game.get_state().sectors,mission,map_weapons=True)
        sensors=Sensors(mission.data['door_sectors'],mission.data['doors'],weapon_sensor=True)
        raw,s=sensors.read(game,0);mission.observe(s,raw.sectors);controller.observe(s,0,raw.sectors)
        item=next(i for i in controller.known.values() if i['name']=='SuperShotgun')
        enemy=min(s['enemies'],key=lambda e:e['distance']);command=dict(action='pickup',target=copy.deepcopy(item),combat_target=None if hold else copy.deepcopy(enemy),weapon=2,decision_id=1,command='pickup',expires_tick=1400)
        controller.accept(command,0);fired=0;damage_start=s['damagecount'];collected=False;path=[]
        for tick in range(1050):
            raw,s=sensors.read(game,tick);mission.observe(s,raw.sectors);controller.observe(s,tick,raw.sectors)
            if command['target']['id'] not in controller.known:
                candidates=[i for i in controller.known.values() if i['name']=='SuperShotgun' and abs(i['x']-item['x'])<8 and abs(i['y']-item['y'])<8]
                if candidates:
                    command=dict(command,target=copy.deepcopy(candidates[0]));controller.accept(command,tick)
            buttons,refs=controller.act(s,tick);fired+=bool(buttons[5])
            if tick%35==0:path.append(dict(tick=tick,x=s['x'],y=s['y'],hp=s['hp'],execution=s['execution']))
            if s['inventory']['8']['owned']:collected=True;break
            game.make_action(buttons,1)
            if game.is_episode_finished():break
        return dict(source_type='mechanical_fixture_explicit_targets',model_inference=False,seed=seed,hold_fire=hold,modified_wad=False,monsters=True,collected=collected,ticks=tick,fire_ticks=fired,damage=s['damagecount']-damage_start,command=command,path=path)
    finally:game.close()


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,required=True);p.add_argument('--hold',action='store_true');a=p.parse_args()
    if a.output.exists():p.error('output exists')
    result=probe(54,a.hold);a.output.write_text(json.dumps(result,indent=2));print(json.dumps({k:v for k,v in result.items() if k not in ('path','command')},indent=2))
    if not result['collected'] or (not a.hold and not result['fire_ticks']):raise SystemExit(1)

if __name__=='__main__':main()
