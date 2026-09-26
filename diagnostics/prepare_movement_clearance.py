"""Measure static local geometry at recorded combat coordinates."""
import argparse
import hashlib
import json
import sys
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from agent import make_game,BUTTONS
from executor import Executor
from mission import Mission,map_data


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('run',type=Path);p.add_argument('--output',type=Path,required=True)
    p.add_argument('--start',type=float,default=422);p.add_argument('--end',type=float,default=427);p.add_argument('--episode',type=int,default=0);a=p.parse_args()
    if a.output.exists():p.error('output exists')
    decisions=[d for d in map(json.loads,(a.run/'decisions.jsonl').open()) if d['episode']==a.episode and a.start<d['tick']/35<a.end and 'movement' in d['answers']]
    if not decisions:p.error('no movement decisions in this interval')
    needed={d['tick'] for d in decisions};states={}
    for row in map(json.loads,(a.run/'telemetry.jsonl').open()):
        if row['tick'] in needed:states[row['tick']]=row
        if row['tick']>max(needed):break
    config=json.loads((a.run/'config.json').read_text())['args']
    game=make_game(SimpleNamespace(map=config['map'],skill=config['skill'],seed=config['seed'],show=False,sound=False,weapon_sensor=config['weapon_sensor']),no_monsters=True)
    try:
        game.make_action([0]*len(BUTTONS),12)
        mission=Mission(map_data(game.get_doom_game_path(),config['map'],config['skill']));nav=Executor(game.get_state().sectors,mission).navigator;rows=[]
        for d in decisions:
            s=states[d['tick']];nav.observe(s,s['tick']);clearance=nav.movement_clearance(s);floor=nav.floors[nav.nearest((s['x'],s['y']))]
            if abs(floor-s['z'])>.01:raise ValueError('Static local floor differs from recorded position; replay moving sectors instead')
            rows.append(dict(tick=d['tick'],seconds=d['tick']/35,hp=s['hp'],x=s['x'],y=s['y'],z=s['z'],static_grid_floor=floor,clearance=clearance,choice=d['answers']['movement']['choice'],state=d['state'],question=d['packet']['questions']['movement']))
        def digest(path):
            with path.open('rb') as handle:return hashlib.file_digest(handle,'sha256').hexdigest()
        report=dict(note='Geometry probe at recorded coordinates using initial map sectors and recorded keys/doors. No monsters and no model gameplay. Local grid floor matches the observed floor; moving-sector replay is not performed.',source_run=str(a.run),source_sha256={name:digest(a.run/name) for name in ('config.json','decisions.jsonl','telemetry.jsonl')},cases=rows)
        a.output.write_text(json.dumps(report,indent=2));print(json.dumps(dict(cases=len(rows),floor_matches=True),indent=2))
    finally:game.close()


if __name__=='__main__':main()
