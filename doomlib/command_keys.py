"""Expose already observed reachable keys; retain every root action for the model."""
import copy,re
FORMAT='command-key-facts-v1'


def command_key_input(state,question):
    lines=state.splitlines();reachable=[line for line in lines if line.startswith('Reachable items:')]
    if len(reachable)!=1:raise ValueError('Missing or ambiguous reachable-item observation')
    available=set(re.findall(r'(\w+)#([^\s,;.]+)',reachable[0]))
    keys=[f'{name}#{key} {distance}m' for name,key,category,distance in re.findall(r'(\w+)#([^\s,;.]+) \[(\w+)\] ([0-9.]+)m',state) if category=='Key' and (name,key) in available]
    prefix='Reachable keys: '+('; '.join(keys) if keys else 'none')+'.'
    facts='\n'.join(line for line in lines if not line.startswith('Current command:'))
    return prefix+'\n'+facts,copy.deepcopy(question)
