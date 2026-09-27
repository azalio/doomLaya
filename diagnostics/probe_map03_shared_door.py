"""MAP03 two-button shared-door fixture; modified spawn, no monsters, no model."""
import argparse
import json
import struct
import sys
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import vizdoom
from agent import make_game, BUTTONS, Sensors
from doomlib.mission import Mission, map_data
from doomlib.executor import Executor


def run_fixture(output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    wad = bytearray((Path(vizdoom.__file__).parent / 'freedoom2.wad').read_bytes())
    count, offset = struct.unpack_from('<ii', wad, 4)
    entries = [struct.unpack_from('<ii8s', wad, offset+i*16) for i in range(count)]
    index = next(i for i, e in enumerate(entries) if e[2].rstrip(b'\0') == b'MAP03')
    start, size, _ = next(e for e in entries[index+1:index+11] if e[2].rstrip(b'\0') == b'THINGS')
    for i in range(start, start+size, 10):
        if struct.unpack_from('<hhhhh', wad, i)[3] == 1:
            struct.pack_into('<hhh', wad, i, 2400, -464, 90)
            break
    fixture = output / 'fixture.wad'
    fixture.write_bytes(wad)
    game = make_game(SimpleNamespace(map='MAP03', skill=3, seed=54, show=False, sound=False), no_monsters=True)
    game.close()
    game.set_doom_game_path(str(fixture.resolve()))
    game.init()
    history = []
    opened = None
    try:
        game.make_action([0]*len(BUTTONS), 12)
        mission = Mission(map_data(game.get_doom_game_path(), 'MAP03'))
        sensors = Sensors(mission.data['door_sectors'], mission.data['doors'])
        controller = Executor(game.get_state().sectors, mission)
        controller.known['fixture_goal']=dict(id='fixture_goal',name='Fixture goal',category='Ammo',x=2400,y=720)
        phase='first_button';closed_again=False;unused_available=False;first_open=None;reopened=None
        for tick in range(1400):
            raw,state=sensors.read(game,tick)
            mission.observe(state,raw.sectors);controller.observe(state,tick,raw.sectors)
            height=raw.sectors[165].ceiling_height-raw.sectors[165].floor_height
            switches={s['id']:s for s in state['switches']}
            if phase=='first_button' and height>=56:first_open=tick;phase='cross_trigger'
            if phase=='cross_trigger' and state['y']>660 and height<8:
                closed_again=True;unused_available=not switches[1863]['activated'];phase='second_button'
            if phase=='second_button' and height>=56:reopened=tick;break
            if phase=='cross_trigger':action='pickup';target=dict(controller.known['fixture_goal'])
            else:action='use_switch';target=dict(switches[1455 if phase=='first_button' else 1863])
            controller.accept(dict(action=action,target=target,weapon=None,decision_id=tick+1,command=action,expires_tick=tick+70),tick)
            buttons,refs=controller.act(state,tick)
            history.append(dict(tick=tick,phase=phase,x=state['x'],y=state['y'],height=height,execution=state['execution'],buttons=buttons))
            game.make_action(buttons,1)
        from PIL import Image
        Image.fromarray(raw.screen_buffer).save(output/'last.png')
        (output/'last-state.json').write_text(json.dumps(state,indent=2))
        reach=controller.navigator.reachable((state['x'],state['y']))
        route_after=controller.navigator.nearest((2400,-464)) in reach
    finally:
        game.close()
    result=dict(note=__doc__,first_open_tick=first_open,closed_again=closed_again,unused_second_button_available=unused_available,reopened_tick=reopened,route_after=route_after,history=history)
    (output/'result.json').write_text(json.dumps(result, indent=2))
    return result


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    if args.output.exists():
        parser.error('output already exists')
    result = run_fixture(args.output)
    print(json.dumps({k:v for k,v in result.items() if k != 'history'}, indent=2))
    raise SystemExit(result['reopened_tick'] is None or not result['route_after'])
