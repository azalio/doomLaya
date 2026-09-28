"""Offline target-continuation counterfactual; never used by the live controller.

Keep recorded movement, use and weapon buttons. Recompute only aim and fire.
The alternative retains one initially observed target while it remains known;
it prepends that target to each recorded firing plan, with at most three members.
Every branch starts from the same replayed prefix. This is not model inference.
"""
import argparse,copy,json,sys
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import vizdoom
from agent import BUTTONS,Sensors,make_game
from doomlib.executor import Executor


def probe(run,start,end,output,target_id=None):
    config=json.loads((run/'config.json').read_text())['args'];rows=[]
    for row in map(json.loads,(run/'telemetry.jsonl').open()):
        if row['tick']>=end:break
        rows.append(row)
    window=[r for r in rows if r['tick']>=start]
    if len(window)!=end-start or len({r['episode'] for r in window})!=1:raise ValueError('Incomplete window or episode boundary')
    decisions={r['directive']['decision_id']:r for r in map(json.loads,(run/'decisions.jsonl').open())}
    directives={key:row['directive'] for key,row in decisions.items()}
    original=directives[window[0]['execution']['decision_id']]
    if original['action']!='attack':raise ValueError('Start with an explicit attack')
    target_id=original['target']['id'] if target_id is None else target_id
    first=next((e for e in window[0]['enemies'] if e['id']==target_id),None)
    if first is None:raise ValueError('The retained target must be observed at window start')
    results=[]
    for variant in ('recorded','recomputed','continue_observed_target','relabeled_recorded_targets'):
        game=make_game(SimpleNamespace(**config));sensors=Sensors(weapon_sensor=True);history=[];target_removed=None
        def values():return {k:float(game.get_game_variable(getattr(vizdoom.GameVariable,v))) for k,v in [('x','POSITION_X'),('y','POSITION_Y'),('z','POSITION_Z'),('hp','HEALTH'),('kills','KILLCOUNT')]}
        try:
            game.make_action([0.]*len(BUTTONS),12)
            for row in rows:
                if row['tick']>=start:break
                if game.is_episode_finished():game.new_episode();game.make_action([0.]*len(BUTTONS),12);sensors=Sensors(weapon_sensor=True)
                if row['tick']>=start-70:sensors.read(game,row['tick'])
                game.set_action(row['buttons']);game.advance_action(1,row['tick']>=start-71)
            initial=values()
            if max(abs(initial[k]-window[0][k]) for k in initial)>.01:raise RuntimeError('Prefix mismatch')
            executor=Executor(game.get_state().sectors,attack_turn_rate=config.get('attack_turn_rate',9));accepted_id=None
            for row in window:
                if game.is_episode_finished():break
                tick=row['tick'];raw,s=sensors.read(game,tick);buttons=list(row['buttons'])
                if target_removed is None and target_id not in {e['id'] for e in s['enemies']}:target_removed=tick
                if variant!='recorded':
                    directive=copy.deepcopy(directives[row['execution']['decision_id']])
                    if directive['action']=='attack' and accepted_id!=directive['decision_id']:
                        if variant=='relabeled_recorded_targets':
                            from training.build_map3_enemy_sequences import order_for
                            packet=decisions[directive['decision_id']]['packet']
                            order=order_for(packet)
                            directive['target_sequence']=[copy.deepcopy(packet['targets']['enemy'][key]) for key in order]
                            directive['target']=directive['target_sequence'][0]
                        if variant=='continue_observed_target' and target_removed is None:
                            current=next(e for e in s['enemies'] if e['id']==target_id)
                            sequence=[current]+[e for e in directive.get('target_sequence',[directive['target']]) if e['id']!=target_id]
                            directive['target_sequence']=sequence[:3];directive['target']=sequence[0]
                        executor.accept(directive,tick);accepted_id=directive['decision_id']
                    if directive['action']=='attack':
                        computed,_=executor.act(s,tick);buttons[4:6]=computed[4:6]
                if variant in ('recorded','recomputed'):
                    if max(abs(s[k]-row[k]) for k in initial)>.01:raise RuntimeError(variant+' baseline state diverged')
                    if max(abs(a-b) for a,b in zip(buttons,row['buttons']))>.00001:raise RuntimeError(variant+' baseline buttons differ')
                history.append(dict(tick=tick,hp=s['hp'],kills=s['kills'],buttons=buttons));game.make_action(buttons,1)
            result=dict(variant=variant,initial=initial,final=values(),dead=game.is_player_dead(),ticks=len(history),first_target_removed=target_removed,fire_ticks=sum(bool(r['buttons'][5]) for r in history),history=history);results.append(result);print({k:v for k,v in result.items() if k!='history'},flush=True)
        finally:game.close()
    output.write_text(json.dumps(dict(note=__doc__,source_run=str(run),start=start,end=end,first_target=first,results=results),indent=2))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('run',type=Path);p.add_argument('--start',type=int,required=True);p.add_argument('--end',type=int,required=True);p.add_argument('--target-id',type=int);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    if a.output.exists():p.error('Output exists')
    probe(a.run,a.start,a.end,a.output,a.target_id)
