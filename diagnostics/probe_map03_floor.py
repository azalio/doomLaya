"""MAP03 exit-floor fixture, with a modified spawn and no monsters; not a model run."""
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
            struct.pack_into('<hhh', wad, i, 3696, -392, 270)
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
        goal = mission.objective()
        route_counts = {}
        for tick in range(210):
            raw, state = sensors.read(game, tick)
            mission.observe(state, raw.sectors)
            controller.observe(state, tick, raw.sectors)
            if tick == 0:
                reach = controller.navigator.reachable((state['x'], state['y']))
                before = controller.navigator.nearest(goal) in reach
                route_counts['before'] = len(reach)
            target = next(s for s in state['switches'] if s['id'] == 2839)
            if tick % 18 == 0:
                controller.accept(dict(action='use_switch', target=dict(target), weapon=None, decision_id=tick+1, command='use_switch', expires_tick=tick+70), tick)
            buttons, refs = controller.act(state, tick)
            height = raw.sectors[306].floor_height
            history.append(dict(tick=tick, position=[state['x'],state['y'],state['z']], angle=state['angle'], height=height, execution=state['execution'], buttons=buttons, refs=refs))
            if controller.navigator.nearest(goal) in controller.navigator.reachable((state['x'], state['y'])):
                opened = tick
                break
            game.make_action(buttons, 1)
        reach = controller.navigator.reachable((state['x'], state['y']))
        after = controller.navigator.nearest(goal) in reach
        route_counts['after'] = len(reach)
        route_counts['switches'] = {s['id']: controller.navigator.nearest(s['approach']) in reach for s in mission.data['switches']}
        route_counts['keys'] = {s['id']: controller.navigator.nearest((s['x'],s['y'])) in reach for s in mission.data['key_markers']}
    finally:
        game.close()
    result = dict(note=__doc__, opened_tick=opened, height=height, route_before=before, route_after=after, routes=route_counts, history=history)
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
    raise SystemExit(result['opened_tick'] is None or not result['route_after'])
