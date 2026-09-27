"""Observed resources for a trained item head; all offered items stay available."""
import copy,re
FORMAT='item-compact-v1'


def compact_item_input(state,question):
    if question.get('type')!='choice' or not question.get('criteria'):raise ValueError('Expected item choices')
    lines=state.splitlines();selected=[]
    for prefix in ('HP ','Inventory:'):
        matching=[line for line in lines if line.startswith(prefix)]
        if len(matching)!=1:raise ValueError('Missing or ambiguous item observation: '+prefix)
        selected.append(matching[0])
    hp=re.fullmatch(r'HP ([0-9.]+); armor ([0-9.]+)\.',selected[0])
    if hp is None:raise ValueError('Invalid health/armor observation')
    health,armor=map(float,hp.groups())
    selected.append('Health below 35: '+('yes' if health<35 else 'no')+'; below 45: '+('yes' if health<45 else 'no')+'; below 85: '+('yes' if health<85 else 'no')+'.')
    selected.append('Armor below 60: '+('yes.' if armor<60 else 'no.'))
    for prefix in ('Collected keys:','Reachable items:'):
        matching=[line for line in lines if line.startswith(prefix)]
        if len(matching)>1:raise ValueError('Ambiguous item observation: '+prefix)
        selected.extend(matching)
    return '\n'.join(selected),copy.deepcopy(question)


CATEGORY_FORMAT='item-category-v2'


def category_item_input(state,question):
    selected,result=compact_item_input(state,question)
    facts={key:(name,category) for name,key,category in re.findall(r'(\w+)#([^ ]+) \[(\w+)\]',state)}
    for key,description in result['criteria'].items():
        if key not in facts:raise ValueError('Missing observed item category: '+key)
        name,category=facts[key]
        if category not in ('Health','Armor','Ammo','Weapon','Key','Powerup'):raise ValueError('Unknown observed item category')
        if not description.startswith(name):raise ValueError('Item category/name mismatch')
        match=re.fullmatch(r'(\w+); (unreachable|reachable)(?:; ((?:not )?owned))?; ([0-9.]+)m\.',description)
        if match is None:raise ValueError('Unrecognized observed item description')
        _,reach,owned,distance=match.groups()
        result['criteria'][key]=distance+'m '+category+' '+name+' '+reach+((' unowned' if owned=='not owned' else ' owned') if owned else '')
    return selected,result
