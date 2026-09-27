"""Project sequence-head state to observed health and inventory; target facts remain in the question."""
import copy
FORMAT='enemy-compact-v1'


def compact_enemy_input(state,question):
    instructions=question['instructions']
    if not instructions.startswith('Choose a firing sequence.') or 'Latest accepted target:' not in instructions or 'Targets:' not in instructions:
        raise ValueError('Compact enemy input requires an explicit firing-sequence question')
    lines=[]
    for prefix in ('HP ','Inventory:'):
        matching=[line for line in state.splitlines() if line.startswith(prefix)]
        if len(matching)!=1:raise ValueError('Missing or ambiguous enemy observation: '+prefix)
        lines.append(matching[0])
    return '\n'.join(lines),copy.deepcopy(question)
