"""Replay recorded buttons and inspect rendered monster pixels around health loss. Offline only."""
import argparse,json,sys,math
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import numpy as np
from PIL import Image
from agent import BUTTONS,Sensors,make_game


def trace(run,start,end,output):
    if output.exists():raise ValueError('Output already exists')
    config=json.loads((run/'config.json').read_text())['args']
    game=make_game(SimpleNamespace(**config));sensors=Sensors(weapon_sensor=True)
    records=[];previous_hp=None;frames=output.with_suffix('');frames.mkdir(parents=True)
    try:
        game.make_action([0.]*len(BUTTONS),12)
        for line in (run/'telemetry.jsonl').open():
            row=json.loads(line);tick=row['tick']
            if tick>=end:break
            if game.is_episode_finished():
                game.new_episode();game.make_action([0.]*len(BUTTONS),12);sensors=Sensors(weapon_sensor=True)
            if tick>=start-70:
                raw,state=sensors.read(game,tick)
                for key in ('x','y','z','hp','kills'):
                    if abs(state[key]-row[key])>.01:raise RuntimeError(f'Recorded prefix mismatch at {tick}: {key}')
                if tick>=start:
                    damage=0 if previous_hp is None else max(0,previous_hp-state['hp'])
                    labels=[]
                    for label in raw.labels:
                        if str(label.object_category)!='Monster':continue
                        ys,xs=np.where(raw.labels_buffer==label.value)
                        labels.append(dict(id=label.object_id,name=label.object_name,xyz=[label.object_position_x,label.object_position_y,label.object_position_z],pixels=int(xs.size),bbox=[int(xs.min()),int(ys.min()),int(xs.max()),int(ys.max())] if xs.size else None))
                    nearby=[dict(id=o.id,name=o.name,xyz=[o.position_x,o.position_y,o.position_z]) for o in raw.objects if math.hypot(o.position_x-state['x'],o.position_y-state['y'])<640]
                    records.append(dict(tick=tick,episode=row['episode'],seconds=tick/35,damage=damage,state={k:state[k] for k in ('x','y','z','hp','angle','kills','enemies')},labels=labels,nearby_objects=nearby,execution=row['execution'],buttons=row['buttons']))
                    if damage or tick%7==0:
                        image=raw.screen_buffer
                        if image.shape[0]==3:image=image.transpose(1,2,0)
                        Image.fromarray(image).save(frames/f'{tick}.png')
                previous_hp=state['hp']
            game.set_action(row['buttons']);game.advance_action(1,tick>=start-71)
        output.write_text(json.dumps(dict(note=__doc__+' Nearby objects are diagnostic ground truth, never supplied to the live model.',run=str(run),start=start,end=end,records=records),indent=2))
        print(json.dumps(dict(frames=len(records),hp_losses=[dict(tick=r['tick'],hp=r['state']['hp'],loss=r['damage'],enemies=r['state']['enemies'],labels=r['labels']) for r in records if r['damage']]),indent=2))
    finally:game.close()


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('run',type=Path);p.add_argument('--start',type=int,required=True);p.add_argument('--end',type=int,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();trace(a.run,a.start,a.end,a.output)
