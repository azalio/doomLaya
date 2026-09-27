"""No-monsters fixture: mapped floor damage versus walking off the floor. Not model gameplay."""
import argparse,json,struct,sys,tempfile
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import vizdoom
from agent import BUTTONS,Sensors,make_game
from doomlib.floor_hazards import FloorHazards


def probe(output):
    rows=[]
    with tempfile.TemporaryDirectory() as directory:
        wad=bytearray((Path(vizdoom.__file__).parent/'freedoom2.wad').read_bytes())
        count,offset=struct.unpack_from('<ii',wad,4);entries=[struct.unpack_from('<ii8s',wad,offset+i*16) for i in range(count)]
        index=next(i for i,e in enumerate(entries) if e[2].rstrip(b'\0')==b'MAP03')
        start,size,_=next(e for e in entries[index+1:index+11] if e[2].rstrip(b'\0')==b'THINGS')
        for i in range(start,start+size,10):
            if struct.unpack_from('<hhhhh',wad,i)[3]==1:struct.pack_into('<hhh',wad,i,2607,298,180);break
        fixture=Path(directory)/'fixture.wad';fixture.write_bytes(wad)
        for move in (False,True):
            game=make_game(SimpleNamespace(map='MAP03',skill=3,seed=54,show=False,sound=False),no_monsters=True)
            game.close();game.set_doom_game_path(str(fixture));game.init();history=[];hits=[];previous=None
            try:
                sensors=Sensors();hazards=FloorHazards(fixture,'MAP03',game.get_state().sectors)
                for tick in range(160):
                    raw,s=sensors.read(game,tick);floor=hazards.observe(s,raw.sectors)
                    if previous is not None and s['hp']<previous:hits.append(dict(tick=tick,amount=previous-s['hp']))
                    previous=s['hp'];history.append(dict(tick=tick,hp=s['hp'],x=s['x'],y=s['y'],z=s['z'],floor=floor))
                    buttons=[0.]*len(BUTTONS);buttons[0]=float(move and tick<30);game.make_action(buttons,1)
                rows.append(dict(walk=move,hits=hits,final_hp=s['hp'],history=history))
            finally:game.close()
    output.write_text(json.dumps(dict(note=__doc__,trials=rows),indent=2))
    for row in rows:print({k:v for k,v in row.items() if k!='history'})
    assert rows[0]['hits'] and all(h['amount']==5 for h in rows[0]['hits'])
    assert all(b['tick']-a['tick']==32 for a,b in zip(rows[0]['hits'],rows[0]['hits'][1:]))
    assert rows[1]['final_hp']>rows[0]['final_hp'] and not rows[1]['history'][-1]['floor']['mapped_damaging_floor']

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.exists():p.error('Output exists')
    probe(a.output)
