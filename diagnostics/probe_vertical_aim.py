"""Controlled aiming fixture with a modified map and inventory; never Laya gameplay."""
import argparse
import hashlib
import json
import math
import struct
import sys
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import vizdoom as vzd
from PIL import Image
from agent import make_game,BUTTONS,wrap,bearing


def fixture_map(output):
    source=Path(vzd.__file__).parent/'freedoom2.wad';wad=bytearray(source.read_bytes())
    count,offset=struct.unpack_from('<ii',wad,4)
    entries=[struct.unpack_from('<ii8s',wad,offset+i*16) for i in range(count)]
    index=next(i for i,e in enumerate(entries) if e[2].rstrip(b'\0')==b'MAP02')
    start,size,_=next(e for e in entries[index+1:index+11] if e[2].rstrip(b'\0')==b'THINGS')
    player=monster=False
    for i in range(start,start+size,10):
        x,y,angle,kind,flags=struct.unpack_from('<hhhhh',wad,i)
        if kind==1 and not player:
            struct.pack_into('<hhhhh',wad,i,1346,-713,100,1,7);player=True
        elif kind==3002 and not monster:
            struct.pack_into('<hhhhh',wad,i,1355,-661,270,3002,7);monster=True
        else:struct.pack_into('<h',wad,i+8,0)
    assert player and monster
    path=output/'fixture.wad';path.write_bytes(wad)
    return path,hashlib.sha256(source.read_bytes()).hexdigest()


def trial(path,output,vertical):
    game=make_game(SimpleNamespace(map='MAP02',skill=3,seed=54,show=False,sound=False))
    game.close();game.set_doom_game_path(str(path.resolve()))
    game.add_game_args('+freelook 1')
    game.set_available_buttons(BUTTONS+[vzd.Button.LOOK_UP_DOWN_DELTA]);game.init()
    def var(name):return float(game.get_game_variable(getattr(vzd.GameVariable,name)))
    history=[];first_visible=None;kill_tick=None
    try:
        game.send_game_command('god');game.send_game_command('freeze')
        game.send_game_command('give shotgun');game.send_game_command('give ammo')
        idle=[0.]*15;game.make_action(idle,2)
        select=list(idle);select[9]=1;game.make_action(select,1);game.make_action(idle,45)
        p0=var('PITCH');calibrate=list(idle);calibrate[-1]=5;game.make_action(calibrate,1)
        scale=wrap(var('PITCH')-p0)/5
        if abs(scale)<.01:raise RuntimeError('Freelook button did not change pitch')
        calibrate[-1]=-5;game.make_action(calibrate,1)
        enemies=[o for o in game.get_state().objects if o.name=='Demon']
        assert len(enemies)==1,len(enemies)
        enemy=enemies[0];target=dict(id=enemy.id,x=enemy.position_x,y=enemy.position_y,z=enemy.position_z)
        initial=dict(position=[var('POSITION_X'),var('POSITION_Y'),var('POSITION_Z')],camera_z=var('CAMERA_POSITION_Z'),pitch=var('PITCH'),target=target,weapon=var('SELECTED_WEAPON'),ammo=var('SELECTED_WEAPON_AMMO'),pitch_per_button_degree=scale)
        for tick in range(210):
            raw=game.get_state();visible=any(l.object_id==target['id'] and l.object_name=='Demon' for l in raw.labels)
            distance=math.hypot(target['x']-var('POSITION_X'),target['y']-var('POSITION_Y'))
            yaw=bearing(target['x'],target['y'],var('POSITION_X'),var('POSITION_Y'),var('ANGLE'))
            desired=math.degrees(math.atan2(var('CAMERA_POSITION_Z')-(target['z']+28),distance))
            pitch=wrap(var('PITCH'));error=wrap(desired-pitch)
            buttons=list(idle);buttons[4]=max(-9,min(9,yaw))
            if vertical:buttons[-1]=max(-9,min(9,error/scale))
            buttons[5]=float(visible and abs(yaw)<5 and (not vertical or abs(error)<5))
            if visible and first_visible is None:first_visible=tick
            kills=int(var('KILLCOUNT'))
            history.append(dict(tick=tick,visible=visible,pitch=pitch,desired_pitch=desired,ammo=var('SELECTED_WEAPON_AMMO'),kills=kills,hits=var('HITCOUNT'),buttons=buttons))
            if tick in (0,20) or kills:Image.fromarray(raw.screen_buffer).save(output/f"{'vertical' if vertical else 'horizontal'}-{tick}.png")
            if kills:kill_tick=tick;break
            game.make_action(buttons,1)
        return dict(vertical=vertical,initial=initial,first_visible_tick=first_visible,kill_tick=kill_tick,final=history[-1],history=history)
    finally:game.close()


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args();a.output.mkdir(exist_ok=False)
    path,source_hash=fixture_map(a.output)
    results=[trial(path,a.output,vertical) for vertical in (False,True)]
    report=dict(note='Non-model fixture: one frozen demon, changed spawn and inventory, invulnerability. Only aim mechanics are compared; this is not level completion.',source_wad_sha256=source_hash,fixture_wad_sha256=hashlib.sha256(path.read_bytes()).hexdigest(),results=results)
    (a.output/'result.json').write_text(json.dumps(report,indent=2));print(json.dumps({**report,'results':[{k:v for k,v in r.items() if k!='history'} for r in results]},indent=2))


if __name__=='__main__':main()
