"""Replay a dead-target pause, changing only the already-selected movement buttons."""
import argparse,json,sys,tempfile
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import vizdoom
from agent import BUTTONS,make_game


def probe(run,start,end,output):
    config=json.loads((run/'config.json').read_text());game=make_game(SimpleNamespace(**config['args']))
    try:
        game.make_action([0.]*len(BUTTONS),12);window=[]
        for line in (run/'telemetry.jsonl').open():
            row=json.loads(line)
            if row['tick']<start:
                if game.is_episode_finished():game.new_episode();game.make_action([0.]*len(BUTTONS),12)
                game.make_action(row['buttons'],1)
            elif row['tick']<end:window.append(row)
            else:break
        first=window[0]
        if first['tick']!=start or len(window)!=end-start:raise ValueError('Incomplete replay window')
        fields=dict(x='POSITION_X',y='POSITION_Y',z='POSITION_Z',hp='HEALTH')
        def state():return {k:float(game.get_game_variable(getattr(vizdoom.GameVariable,v))) for k,v in fields.items()}
        before=state()
        if max(abs(before[k]-first[k]) for k in before)>.01:raise RuntimeError('Replay diverged')
        for row in window:
            if row['execution']['action']!='attack' or row['execution']['status']!='unavailable' or any(row['buttons'][:7]):raise ValueError('Window is not exclusively the observed dead-target pause')
        trials=[]
        with tempfile.TemporaryDirectory() as directory:
            save=str(Path(directory)/'pause.zds');game.save(save)
            for keep in (False,True):
                game.new_episode();game.load(save);history=[]
                for row in window:
                    if game.is_episode_finished():break
                    buttons=list(row['buttons'])
                    if keep:
                        index={'strafe_left':2,'strafe_right':3,'backward':1}.get(row['execution'].get('movement'))
                        if index is not None:buttons[index]=1
                    history.append(dict(tick=row['tick'],buttons=buttons,**state()));game.make_action(buttons,1)
                trials.append(dict(preserve_model_movement=keep,final=state(),dead=game.is_player_dead(),ticks=len(history),history=history))
        report=dict(note=__doc__+' Diagnostic only, not model gameplay. Both branches replay the same recorded choices and use the same saved engine state; no new targets or movement directions are selected.',source_run=str(run),start=start,end=end,replay_matches=True,before=before,trials=trials)
        output.write_text(json.dumps(report,indent=2));print(json.dumps({**report,'trials':[{k:v for k,v in t.items() if k!='history'} for t in trials]},indent=2))
    finally:game.close()


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('run',type=Path);p.add_argument('--start',type=int,required=True);p.add_argument('--end',type=int,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();probe(a.run,a.start,a.end,a.output)
