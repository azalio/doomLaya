"""Mechanical MAP01 exit fixture: altered spawn/open door, no monsters or model."""
import argparse,json,struct,sys
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import vizdoom
from agent import make_game,BUTTONS,Sensors
from doomlib.mission import Mission,map_data
from doomlib.executor import Executor


def probe(output):
    output.mkdir();wad=bytearray((Path(vizdoom.__file__).parent/'freedoom2.wad').read_bytes());count,offset=struct.unpack_from('<ii',wad,4)
    entries=[struct.unpack_from('<ii8s',wad,offset+i*16) for i in range(count)];index=next(i for i,e in enumerate(entries) if e[2].rstrip(b'\0')==b'MAP01');lumps={e[2].rstrip(b'\0').decode():e for e in entries[index+1:index+11]}
    start,size,_=lumps['THINGS']
    for i in range(start,start+size,10):
        if struct.unpack_from('<hhhhh',wad,i)[3]==1:struct.pack_into('<hhh',wad,i,225,-592,270);break
    # Recreate the recorded state after the exit-passage switch opened sector 208.
    sector=lumps['SECTORS'][0]+208*26;floor=struct.unpack_from('<h',wad,sector)[0];struct.pack_into('<h',wad,sector+2,floor+128)
    path=output/'fixture.wad';path.write_bytes(wad)
    game=make_game(SimpleNamespace(map='MAP01',skill=3,seed=48,show=False,sound=False),no_monsters=True);game.close();game.set_doom_game_path(str(path.resolve()));game.init();history=[]
    try:
        game.make_action([0.]*len(BUTTONS),12);mission=Mission(map_data(path,'MAP01'));sensors=Sensors(mission.data['door_sectors'],mission.data['doors']);controller=Executor(game.get_state().sectors,mission)
        for tick in range(350):
            if game.is_episode_finished():break
            raw,state=sensors.read(game,tick);mission.observe(state,raw.sectors);controller.observe(state,tick,raw.sectors)
            if tick%18==0:controller.accept(dict(action='exit',target=None,weapon=None,decision_id=tick+1,command='exit',expires_tick=tick+70),tick)
            buttons,refs=controller.act(state,tick);history.append(dict(tick=tick,x=state['x'],y=state['y'],z=state['z'],angle=state['angle'],buttons=buttons,refs=refs));game.make_action(buttons,1)
        report=dict(note=__doc__,episode_finished=game.is_episode_finished(),dead=game.is_player_dead(),ticks=len(history),history=history)
    finally:game.close()
    (output/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({k:v for k,v in report.items() if k!='history'}));return report['episode_finished'] and not report['dead']


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args();raise SystemExit(not probe(a.output))
