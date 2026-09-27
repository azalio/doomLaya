"""Observed health-loss history and an explicit, optional look-back command."""
import copy
from collections import deque

LOOK_DESCRIPTION='Turn clockwise 180 degrees to inspect behind you. Do not walk or fire. Stop after the half turn.'


class DamageHistory:
    def __init__(self,window_ticks=70):
        self.window_ticks=window_ticks
        self.episode=None
        self.previous_hp=None
        self.hits=deque()
        self.last_look_tick=-1
        self.look_was_complete=False

    def observe(self,state,tick,episode):
        if self.episode!=episode:
            self.episode=episode;self.previous_hp=None;self.hits.clear()
            self.last_look_tick=-1;self.look_was_complete=False
        if self.previous_hp is not None and state['hp']<self.previous_hp:
            self.hits.append((tick,self.previous_hp-state['hp']))
        self.previous_hp=state['hp']
        while self.hits and tick-self.hits[0][0]>self.window_ticks:self.hits.popleft()
        execution=state.get('execution') or {}
        complete=execution.get('action')=='look_back' and execution.get('status')=='arrived'
        if complete and not self.look_was_complete:self.last_look_tick=tick
        self.look_was_complete=complete
        return dict(hp_loss=sum(loss for _,loss in self.hits),
                    latest_age_seconds=round((tick-self.hits[-1][0])/35,3) if self.hits else None,
                    looked_after_hit=bool(self.hits and self.last_look_tick>=self.hits[-1][0]))


def look_question(question,facts,status='inactive'):
    result=copy.deepcopy(question)
    age=facts['latest_age_seconds']
    detail=f'{age:.1f}s ago' if age is not None else 'none'
    prefix=(f"Recent health loss (last 2 seconds): {facts['hp_loss']:g} HP. Latest hit: {detail}. "
            f"Look back completed since latest hit: {'yes' if facts['looked_after_hit'] else 'no'}. "
            f"Look back status: {status}. ")
    result['instructions']=prefix+result['instructions']
    result['criteria']['look_back']=LOOK_DESCRIPTION
    return result


def with_look_action(packet,facts):
    result=copy.deepcopy(packet)
    execution=result.get('observation',{}).get('execution') or {}
    status=execution.get('status','inactive') if execution.get('action')=='look_back' else 'inactive'
    result['questions']['command']=look_question(result['questions']['command'],facts,status)
    result['commands']['look_back']=dict(action='look_back',target=None)
    result['look_facts']=dict(facts,status=status)
    return result


LOOK_GATE_QUESTION=dict(type='choice',instructions='Choose whether to inspect behind the player or let normal command selection proceed. Use observed health loss, known enemies and completed turns.',criteria={'normal':'Proceed with normal selection of attacks, items, mechanisms and routes.','look_back':'Turn clockwise 180 degrees to look behind the player, without walking or firing.'})


def look_gate_input(facts):
    import math
    loss=facts['hp_loss'];age=facts['latest_age_seconds'];count=facts['known_enemy_count']
    if not isinstance(loss,(int,float)) or not math.isfinite(loss) or loss<0:raise ValueError('Invalid observed HP loss')
    if age is not None and (not isinstance(age,(int,float)) or not math.isfinite(age) or age<0):raise ValueError('Invalid hit age')
    if type(count) is not int or count<0:raise ValueError('Invalid known enemy count')
    if type(facts['looked_after_hit']) is not bool:raise ValueError('Invalid completed-look fact')
    if facts['status'] not in ('inactive','executing','arrived'):raise ValueError('Invalid look status')
    age_text=f'{age:.1f} seconds ago' if age is not None else 'none'
    state=(f"Health lost recently: {'yes' if loss>0 else 'no'}. Amount: {loss:g} HP.\n"
           f"Latest hit: {age_text}.\nKnown enemies: {count}.\n"
           f"Look completed since latest hit: {'yes' if facts['looked_after_hit'] else 'no'}.\n"
           f"Current look status: {facts['status']}.")
    if 'standing_on_damaging_floor' in facts:
        floor=facts['standing_on_damaging_floor']
        if type(floor) is not bool:raise ValueError('Invalid mapped floor fact')
        state+="\nStanding on a mapped damaging floor: "+('yes.' if floor else 'no.')
    return state,copy.deepcopy(LOOK_GATE_QUESTION)


def with_look_gate(packet,facts):
    result=copy.deepcopy(packet);execution=result.get('observation',{}).get('execution') or {}
    status=execution.get('status','inactive') if execution.get('action')=='look_back' else 'inactive'
    observed=dict(facts,status=status,known_enemy_count=len(result.get('targets',{}).get('enemy',{})))
    look_gate_input(observed)
    result['questions']['command']['look_observation']=observed
    result['questions']['command']['criteria']['look_back']=LOOK_DESCRIPTION
    result['commands']['look_back']=dict(action='look_back',target=None)
    result['look_facts']=observed
    return result


def mix_look_answer(base,gate,keys):
    """A two-head probability mixture; relative regular-action scores are preserved."""
    import math
    if set(gate['probabilities'])!={'normal','look_back'}:raise ValueError('Invalid look-gate choices')
    if set(base['probabilities'])!=set(keys)-{'look_back'}:raise ValueError('Invalid base command choices')
    def normalized(values):
        if any(not math.isfinite(v) or v<0 for v in values.values()) or sum(values.values())<=0:raise ValueError('Invalid model probabilities')
        total=sum(values.values());return {k:v/total for k,v in values.items()}
    normal=normalized(base['probabilities']);attention=normalized(gate['probabilities'])
    probabilities={k:attention['look_back'] if k=='look_back' else attention['normal']*normal[k] for k in keys}
    result=copy.deepcopy(base);result.update(choice=max(probabilities,key=probabilities.get),probabilities=probabilities,confidence=max(probabilities.values()),look_gate=dict(answer=copy.deepcopy(gate),base_answer=copy.deepcopy(base),composition='probability-mixture-v1'))
    return result
