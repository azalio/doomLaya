"""Learned item-score residual from observed resources, without a runtime rubric."""
import copy
import math
import re
from doomlib.combat import WEAPON_NAMES, AMMO_COST
from doomlib.items import WEAPONS
from doomlib.compact_item import CATEGORY_FORMAT

FORMAT='laya-item-numeric-residual-v1'
CATEGORIES=('Health','Armor','Ammo','Weapon','Key','Powerup')


def observations(state,question,names):
    hp=re.search(r'^HP ([0-9.]+); armor ([0-9.]+)',state,re.M)
    inventory=next(line for line in state.splitlines() if line.startswith('Inventory:'))
    ammo={name:float(n) for name,n in re.findall(r'(\w+) ([0-9.]+) ammo',inventory)}
    global_values=[float(hp[1])/100,float(hp[2])/100]
    for slot,name in WEAPON_NAMES.items():
        global_values.extend([float(name in ammo),ammo.get(name,0)/100,float(name in ammo and ammo[name]>=AMMO_COST[slot])])
    items=[]
    for key,text in question['criteria'].items():
        match=re.fullmatch(r'([0-9.]+)m (Health|Armor|Ammo|Weapon|Key|Powerup) (\w+) (reachable|unreachable)(?: (owned|unowned))?',text)
        if not match:raise ValueError('Invalid observed item description')
        distance,category,name,reach,_=match.groups()
        items.append((key,float(distance),category,name,reach=='reachable'))
    for category in CATEGORIES:
        distances=[distance for _,distance,c,_,reachable in items if c==category and reachable]
        global_values.extend([float(bool(distances)),min(min(distances,default=256),256)/32,len(distances)/10])
    result=[]
    for key,distance,category,name,reachable in items:
        slot=WEAPONS.get(name);weapon=WEAPON_NAMES.get(slot)
        values=global_values+[min(distance,256)/32,float(reachable)]
        values += [float(category==c) for c in CATEGORIES]+[float(name==n) for n in names]
        values += [float(weapon in ammo),ammo.get(weapon,0)/100]
        result.append(values)
    if not result or not all(math.isfinite(x) for row in result for x in row):raise ValueError('Invalid item features')
    return result


def make_model(spec):
    import torch
    from torch import nn
    if spec['format']!=FORMAT or spec['input_projection']!=CATEGORY_FORMAT or spec['question']!='item':raise ValueError('Invalid item residual format')
    width=2+3*len(WEAPON_NAMES)+3*len(CATEGORIES)+2+len(CATEGORIES)+len(spec['item_names'])+2
    if width!=spec['features']:raise ValueError('Item feature schema differs')
    indices=[];thresholds=[]
    for key,values in sorted(spec['thresholds'].items(),key=lambda pair:int(pair[0])):
        index=int(key)
        if not 0<=index<width or not all(math.isfinite(v) for v in values):raise ValueError('Invalid item thresholds')
        indices.extend([index]*len(values));thresholds.extend(values)
    hidden=spec['hidden_size']
    if not isinstance(hidden,int) or not 1<=hidden<=1024:raise ValueError('Invalid item residual width')
    class ItemResidual(nn.Module):
        def __init__(self):
            super().__init__()
            self.register_buffer('basis_indices',torch.tensor(indices,dtype=torch.long))
            self.register_buffer('basis_thresholds',torch.tensor(thresholds,dtype=torch.float32))
            self.semantic_scale=nn.Parameter(torch.ones(()))
            self.network=nn.Sequential(nn.Linear(width+len(indices)+1,hidden),nn.ReLU(),nn.Linear(hidden,hidden),nn.ReLU(),nn.Linear(hidden,1))
            nn.init.zeros_(self.network[-1].weight);nn.init.zeros_(self.network[-1].bias)
        def forward(self,observed,semantic):
            basis=(observed[...,self.basis_indices]>=self.basis_thresholds).to(observed.dtype)
            inputs=torch.cat([observed,basis,semantic[...,None]/10],-1)
            return self.semantic_scale*semantic+self.network(inputs).squeeze(-1)
    return ItemResidual()


def predict(agent,state,questions):
    import torch
    if set(questions)!={'item'}:raise ValueError('Item numeric residual requires one item question')
    question=questions['item'];keys=list(question['criteria']);spec=agent.numeric_residual_spec
    original=agent._semantic_predict(state,questions);answer=original['answers']['item']
    observed=observations(state,question,spec['item_names'])
    base=[math.log(max(float(answer['probabilities'][key]),spec['probability_floor'])) for key in keys]
    with torch.no_grad():
        x=torch.tensor([observed],dtype=torch.float32,device=agent.device)
        b=torch.tensor([base],dtype=torch.float32,device=agent.device)
        scores=agent.numeric_residual(x,b)[0];prob=scores.cpu().double().softmax(-1).tolist();delta=(scores-b[0]).cpu().tolist()
    probabilities=dict(zip(keys,prob));choice=max(probabilities,key=probabilities.get)
    result=dict(type='choice',choice=choice,probabilities=probabilities,confidence=probabilities[choice],action=copy.deepcopy(answer.get('action',{})),
        numeric_residual=dict(composition=FORMAT,semantic_answer=answer,logit_delta=dict(zip(keys,delta))))
    return dict(original,answers={'item':result})
