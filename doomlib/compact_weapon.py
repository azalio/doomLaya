"""Weapon-head observations: health, inventory and currently known enemies."""
import copy,re
FORMAT='weapon-compact-v1'


def compact_weapon_input(state,question):
    if question.get('type')!='choice' or 'keep' not in question.get('criteria',{}):raise ValueError('Expected explicit weapon choices')
    health=[line for line in state.splitlines() if line.startswith('HP ') or line.startswith('The player has ')]
    inventory=[line for line in state.splitlines() if line.startswith('Inventory:')]
    if len(health)!=1 or len(inventory)!=1:raise ValueError('Missing or ambiguous weapon facts')
    hp=re.sub(r'The player has ([0-9.]+) health and ([0-9.]+) armor\.',r'HP \1; armor \2.',health[0])
    enemies=[line for line in state.splitlines() if line.startswith(('Enemies:','Hostile enemies currently visible','No enemies visible'))]
    if len(enemies)>1:raise ValueError('Ambiguous enemy facts')
    return '\n'.join([hp,inventory[0]]+enemies),copy.deepcopy(question)
