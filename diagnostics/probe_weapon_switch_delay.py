"""Isolate engine weapon transitions; granted inventory is diagnostic setup only."""
import argparse
import json
import sys
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from agent import BUTTONS, Sensors, make_game


def trial(fire_ticks,repeat):
    game=make_game(SimpleNamespace(map='MAP02',skill=3,seed=54,show=False,sound=False,weapon_sensor=True),no_monsters=True)
    idle=[0]*len(BUTTONS);sensor=Sensors(weapon_sensor=True)
    try:
        game.make_action(idle,45)
        game.send_game_command('give shotgun');game.send_game_command('give ammo');game.make_action(idle,2)
        assert sensor.read(game,0)[1]['weapon']==2
        fire=list(idle);fire[5]=1
        if fire_ticks:game.make_action(fire,fire_ticks)
        history=[]
        for tick in range(90):
            s=sensor.read(game,tick)[1]
            buttons=list(idle)
            if tick==0 or repeat and tick%12==0:buttons[9]=1
            history.append(dict(tick=tick,weapon=s['weapon'],bullets=s['inventory']['2']['ammo'],shells=s['inventory']['3']['ammo'],select=buttons[9]))
            if s['weapon']==3:return dict(fire_ticks=fire_ticks,repeat_every_12=repeat,equip_ticks=tick,history=history)
            game.make_action(buttons,1)
        raise RuntimeError('Shotgun never equipped')
    finally:game.close()


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.exists():p.error('output exists')
    records=[]
    for phase in (0,1,4,8,12,16):
        for repeat in (False,True):
            row=trial(phase,repeat);records.append(row);print({k:v for k,v in row.items() if k!='history'},flush=True)
    a.output.write_text(json.dumps(dict(note='No model inference or level-completion claim: monsters disabled and inventory granted to isolate engine weapon switching.',records=records),indent=2))


if __name__=='__main__':main()
