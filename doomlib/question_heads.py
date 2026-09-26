"""Run fixed question-specific Laya heads with one identical frozen encoder."""
import copy
import json
from pathlib import Path


def parse_head_specs(specs,item_checkpoint=None):
    """Validate fixed question routing before loading any checkpoint."""
    names={'command','item','weapon','movement','switch','enemy','combat'}
    result={'item':item_checkpoint} if item_checkpoint else {}
    for spec in specs:
        question,separator,path=spec.partition('=')
        if not separator or question not in names or not path:
            raise ValueError('Expected a known QUESTION=CHECKPOINT: '+spec)
        if question in result:raise ValueError('Duplicate question head: '+question)
        result[question]=path
    return result


class QuestionHeads:
    def __init__(self,base,overrides):
        self.base=base;self.overrides=dict(overrides)

    def predict(self,state,questions):
        groups={}
        for name,question in questions.items():
            agent=self.overrides.get(name,self.base)
            groups.setdefault(id(agent),(agent,{}))[1][name]=question
        answers={};usage={};model=None
        for agent,selected in groups.values():
            result=agent.predict(state,selected);model=result['model']
            if set(result['answers'])!=set(selected):raise ValueError('Head returned unexpected questions')
            answers.update(result['answers'])
            for key,value in result['usage'].items():usage[key]=usage.get(key,0)+value
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
    return agent
