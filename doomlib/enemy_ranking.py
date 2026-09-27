"""Neural target scores define a distribution over the original explicit firing plans."""
import copy,itertools,math,re
from doomlib.compact_enemy import compact_enemy_input
FORMAT='enemy-ranking-v1'
STOP='__stop__'


def ranking_input(state,question):
    state,_=compact_enemy_input(state,question)
    instruction=question['instructions']
    matches=re.findall(r'#([^ ;]+) (\w+) ([0-9.]+)m bearing ([+-]?[0-9]+) degrees (visible|last seen)',instruction.split('Targets: ',1)[1])
    keys=[row[0] for row in matches]
    if not 1<=len(keys)<=3 or len(set(keys))!=len(keys) or STOP in keys:raise ValueError('Invalid enemy ranking targets')
    previous=re.search(r'Latest accepted target: (none|#[^ .]+)\.',instruction)
    if previous is None:raise ValueError('Missing previous target fact')
    current=previous[1].removeprefix('#')
    criteria={key:f'{name}; distance {distance}m; bearing {bearing} degrees; {visibility}; latest accepted target: {"yes" if key==current else "no"}.' for key,name,distance,bearing,visibility in matches}
    criteria[STOP]='End the firing sequence before any remaining targets.'
    orders={}
    for key,description in question['criteria'].items():
        order=re.findall(r'#([^ ,\.]+)',description)
        if not order or len(order)!=len(set(order)) or not set(order)<=set(keys):raise ValueError('Invalid explicit firing plan')
        if description!='Shoot '+', then '.join('#'+oid for oid in order)+'.':raise ValueError('Unrecognized firing plan')
        orders[key]=order
    expected={order for n in range(1,len(keys)+1) for order in itertools.permutations(keys,n)}
    if len(orders)!=len(expected) or {tuple(order) for order in orders.values()}!=expected:raise ValueError('Incomplete explicit firing plans')
    rank_question=dict(type='choice',instructions='Rank the known targets for a firing sequence. Higher scores mean earlier targets. Rank ending the sequence before targets that should be omitted. At least one target is required. A new decision may replace the sequence.',criteria=criteria)
    return state,rank_question,orders


def sequence_probabilities(probabilities,orders):
    keys={target for order in orders.values() for target in order}
    if set(probabilities)!=keys|{STOP}:raise ValueError('Ranking scores do not match available targets')
    if any(not math.isfinite(v) or v<0 for v in probabilities.values()) or sum(probabilities.values())<=0:raise ValueError('Invalid model ranking probabilities')
    # Numerical zero is allowed, but must not make a conditional stage undefined.
    # Learned ranker inference preserves probabilities before API display rounding.
    weights={key:max(float(value),1e-300) for key,value in probabilities.items()}
    result={}
    for key,order in orders.items():
        remaining=set(keys);probability=1.
        for index,target in enumerate(order):
            denominator=sum(weights[k] for k in remaining)+(weights[STOP] if index else 0)
            probability*=weights[target]/denominator;remaining.remove(target)
        if remaining:probability*=weights[STOP]/(weights[STOP]+sum(weights[k] for k in remaining))
        result[key]=probability
    total=sum(result.values())
    if total<=0:raise ValueError('Empty sequence distribution')
    return {key:value/total for key,value in result.items()}


def decode_ranking(answer,orders):
    probabilities=sequence_probabilities(answer['probabilities'],orders)
    choice=max(probabilities,key=probabilities.get)
    return dict(type='choice',choice=choice,probabilities=probabilities,confidence=probabilities[choice],ranking_head=copy.deepcopy(answer),composition='plackett-luce-nonempty-v1')
