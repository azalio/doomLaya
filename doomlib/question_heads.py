"""Run fixed question-specific Laya heads with one identical frozen encoder."""
import copy
import json
from pathlib import Path


def parse_head_specs(specs,item_checkpoint=None):
    """Validate fixed question routing before loading any checkpoint."""
    names={'command','item','weapon','movement','switch','enemy','combat','look_gate'}
    result={'item':item_checkpoint} if item_checkpoint else {}
    for spec in specs:
        question,separator,path=spec.partition('=')
        if not separator or question not in names or not path:
            raise ValueError('Expected a known QUESTION=CHECKPOINT: '+spec)
        if question in result:raise ValueError('Duplicate question head: '+question)
        result[question]=path
    return result


class QuestionHeads:
    def __init__(self,base,overrides,item_without_goal=False,command_without_goal=False,enemy_without_goal=False,movement_compact_facts=False,enemy_compact_facts=False,enemy_rank_facts=False,weapon_compact_facts=False,item_compact_facts=False,item_category_facts=False):
        self.base=base;self.overrides=dict(overrides)
        self.item_without_goal=item_without_goal
        self.command_without_goal=command_without_goal
        self.enemy_without_goal=enemy_without_goal
        self.movement_compact_facts=movement_compact_facts
        self.enemy_compact_facts=enemy_compact_facts
        self.enemy_rank_facts=enemy_rank_facts
        self.weapon_compact_facts=weapon_compact_facts
        self.item_compact_facts=item_compact_facts
        self.item_category_facts=item_category_facts
        if item_compact_facts and item_category_facts:raise ValueError("Choose one item input projection")
        if enemy_compact_facts and enemy_rank_facts:raise ValueError("Choose one enemy input projection")

    def predict(self,state,questions):
        groups={};look_request=None;rank_orders=None
        for name,question in questions.items():
            if name=='command' and 'look_observation' in question:
                if 'look_gate' not in self.overrides:raise ValueError('A learned look_gate head is required')
                if 'look_back' not in question['criteria']:raise ValueError('Missing look-back option')
                look_request=(question['look_observation'],list(question['criteria']))
                question=copy.deepcopy(question);question.pop('look_observation');question['criteria'].pop('look_back')
                if not question['criteria']:raise ValueError('Missing normal command options')
            agent=self.overrides.get(name,self.base)
            project=(self.item_without_goal and name=='item') or (self.command_without_goal and name=='command') or (self.enemy_without_goal and name=='enemy')
            selected_state='\n'.join(line for line in state.splitlines() if not line.startswith('Current command:')) if project else state
            projection='without-current-command-v1' if project else 'full'
            if self.movement_compact_facts and name=='movement':
                from doomlib.compact_movement import compact_movement_input,FORMAT
                selected_state,question=compact_movement_input(state,question);projection=FORMAT
            if self.enemy_compact_facts and name=='enemy':
                from doomlib.compact_enemy import compact_enemy_input,FORMAT
                selected_state,question=compact_enemy_input(state,question);projection=FORMAT
            if self.enemy_rank_facts and name=='enemy':
                from doomlib.enemy_ranking import ranking_input,FORMAT
                selected_state,question,rank_orders=ranking_input(state,question);projection=FORMAT
            if self.weapon_compact_facts and name=='weapon':
                from doomlib.compact_weapon import compact_weapon_input,FORMAT
                selected_state,question=compact_weapon_input(state,question);projection=FORMAT
            if self.item_compact_facts and name=='item':
                from doomlib.compact_item import compact_item_input,FORMAT
                selected_state,question=compact_item_input(state,question);projection=FORMAT
            if self.item_category_facts and name=='item':
                from doomlib.compact_item import category_item_input,CATEGORY_FORMAT
                selected_state,question=category_item_input(state,question);projection=CATEGORY_FORMAT
            groups.setdefault((id(agent),projection),(agent,selected_state,{}))[2][name]=question
        answers={};usage={};model=None
        for agent,selected_state,selected in groups.values():
            result=agent.predict(selected_state,selected);model=result['model']
            if set(result['answers'])!=set(selected):raise ValueError('Head returned unexpected questions')
            answers.update(result['answers'])
            for key,value in result['usage'].items():usage[key]=usage.get(key,0)+value
        if rank_orders is not None:
            from doomlib.enemy_ranking import decode_ranking
            answers['enemy']=decode_ranking(answers['enemy'],rank_orders)
        if look_request is not None:
            from doomlib.look_questions import look_gate_input,mix_look_answer
            facts,keys=look_request;gate_state,gate_question=look_gate_input(facts)
            gate=self.overrides['look_gate'].predict(gate_state,{'command':gate_question})
            answers['command']=mix_look_answer(answers['command'],gate['answers']['command'],keys)
            for key,value in gate['usage'].items():usage[key]=usage.get(key,0)+value
        return dict(model=model,answers={name:answers[name] for name in questions},usage=usage)


def load_head(base,base_path,head_path):
    """Reuse the encoder only after exact checkpoint/tokenizer compatibility checks."""
    import torch
    from safetensors import safe_open
    from laya.common import DecisionModel
    from doomlib.laya_runtime import enable_single_option_padding
    base_path,head_path=Path(base_path),Path(head_path)
    config=json.loads((head_path/'rl_agent_config.json').read_text())
    for name in ('encoder','head_layers','max_len','head_max_len'):
        if config.get(name)!=base.cfg.get(name):raise ValueError('Incompatible head config: '+name)
    for path in (base_path/'tokenizer').rglob('*'):
        if path.is_file() and path.read_bytes()!=(head_path/'tokenizer'/path.relative_to(base_path/'tokenizer')).read_bytes():
            raise ValueError('Incompatible head tokenizer')
    weights={}
    with safe_open(str(base_path/'model.safetensors'),framework='pt',device='cpu') as original,safe_open(str(head_path/'model.safetensors'),framework='pt',device='cpu') as source:
        if set(original.keys())!=set(source.keys()):raise ValueError('Head architecture differs')
        for name in source.keys():
            value=source.get_tensor(name)
            if name.startswith('encoder.'):
                if not torch.equal(value,original.get_tensor(name)):raise ValueError('Head changed the frozen encoder: '+name)
            else:weights[name]=value
    agent=copy.copy(base);agent.cfg=config
    agent.model=DecisionModel(base.model.encoder,config.get('head_layers',2),len(config.get('act_costs',{}))+1)
    missing,unexpected=agent.model.load_state_dict(weights,strict=False)
    if unexpected or any(not name.startswith('encoder.') for name in missing):raise ValueError('Incomplete head weights')
    agent.model.to(device=base.device,dtype=base.dtype).eval();enable_single_option_padding(agent.model)
    agent.temperature=config.get('temperature',[1.,1.,1.]);agent.temperature_by_options=config.get('temperature_by_options',{})
    if config.get('doom_adaptation',{}).get('input_projection')=='enemy-ranking-v1':
        from types import MethodType
        from doomlib.ranked_inference import predict_precise
        agent.predict=MethodType(predict_precise,agent)
    return agent
