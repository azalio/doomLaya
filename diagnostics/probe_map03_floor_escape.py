"""Replay the offline teacher floor trap and compare planned versus direct travel to one fixed point."""
import argparse,json,math,sys
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from agent import BUTTONS,Sensors,make_game
from doomlib.mission import Mission,map_data
from doomlib.executor import Executor
from doomlib.combat import target_bearing


def probe(run,cut,output):
    rows=[json.loads(l) for l in (run/'telemetry.jsonl').read_text().splitlines()];first=rows[cut];results=[]
    config=json.loads((run/'config.json').read_text())
    for variant in ('planned','direct'):
        game=make_game(SimpleNamespace(map='MAP03',skill=3,seed=config['seed'],show=False,sound=False,weapon_sensor=True));sensors=Sensors(weapon_sensor=True)
        try:
            game.make_action([0.]*len(BUTTONS),12)
            initial_geometry=[dict(floor=s.floor_height,ceiling=s.ceiling_height,blocking=[l.is_blocking for l in s.lines]) for s in game.get_state().sectors]
            mission=Mission(map_data(game.get_doom_game_path(),'MAP03'));executor=Executor(game.get_state().sectors,mission)
            for row in rows[:cut]:
                if row['tick']>=cut-70:sensors.read(game,row['tick'])
                game.set_action(row['buttons']);game.advance_action(1,row['tick']>=cut-71)
            raw,state=sensors.read(game,cut)
            for k in ('x','y','z','hp'):
                if abs(state[k]-first[k])>.01:raise RuntimeError('Prefix mismatch: '+k)
            nav=executor.navigator
            start=nav.nearest((state['x'],state['y']));goal=(2400,298);target=dict(id='fixture',name='Fixed safe point',x=goal[0],y=goal[1],category='Health',z=0,distance=7)
            executor.known['fixture']=target;executor.accept(dict(action='pickup',target=target,weapon=None,decision_id=1,command='pickup',expires_tick=cut+175),cut)
            fresh=Executor(raw.sectors,mission).navigator
            changed=[dict(sector=i,before=old,after=dict(floor=sec.floor_height,ceiling=sec.ceiling_height,blocking=[l.is_blocking for l in sec.lines])) for i,(old,sec) in enumerate(zip(initial_geometry,raw.sectors)) if old!=dict(floor=sec.floor_height,ceiling=sec.ceiling_height,blocking=[l.is_blocking for l in sec.lines])]
            details=dict(geometry_changed=changed,missing_direct_cells=[dict(node=list(n),fresh_sectors=fresh.body_sectors.get(n)) for n in fresh.free-nav.free if 2380<fresh.point(n)[0]<2620 and 285<fresh.point(n)[1]<312],start=list(start) if start else None,start_floor=nav.floors.get(start),body_sectors={str(i):nav.sector_heights[i] for i in nav.body_sectors.get(start,())},neighbor_floors={str((start[0]+dx,start[1]+dy)):nav.floors.get((start[0]+dx,start[1]+dy)) for dx,dy in [(-1,0),(1,0),(0,-1),(0,1)]} if start else {})
            history=[]
            for tick in range(cut,cut+150):
                if game.is_episode_finished():break
                raw,state=sensors.read(game,tick);state['keys']=first['keys'];mission.observe(state,raw.sectors);executor.observe(state,tick,raw.sectors)
                if variant=='planned':buttons,refs=executor.act(state,tick)
                else:
                    b=target_bearing(target,state);buttons=[0.]*len(BUTTONS);buttons[4]=max(-6,min(6,b));buttons[0]=float(abs(b)<20 and math.dist((state['x'],state['y']),goal)>20);refs=[]
                history.append(dict(tick=tick,x=state['x'],y=state['y'],z=state['z'],hp=state['hp'],buttons=buttons,refs=refs,navigation=nav.state(tick)))
                game.make_action(buttons,1)
            results.append(dict(variant=variant,details=details,final=history[-1],dead=game.is_player_dead(),history=history));print({k:v for k,v in results[-1].items() if k!='history'},flush=True)
        finally:game.close()
    output.write_text(json.dumps(dict(note=__doc__,source_run=str(run),cut=cut,results=results),indent=2))

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('run',type=Path);p.add_argument('--tick',type=int,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.exists():p.error('Output exists')
    probe(a.run,a.tick,a.output)
