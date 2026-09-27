"""Offer explicit firing orders; execution preserves the model-selected sequence."""
import copy,itertools

QUESTION_FORMAT='enemy-sequence-v1'


def with_enemy_sequences(packet):
    if 'enemy' not in packet['questions']:return packet
    result=copy.deepcopy(packet);enemies=result['targets']['enemy'];keys=list(enemies)
    if not 1<=len(keys)<=3:raise ValueError('Enemy sequences require one to three observed candidates')
    current=(result.get('enemy_commitment') or {}).get('target_id')
    facts='; '.join(f"#{key} {e['name']} {e['distance']:.1f}m bearing {e.get('bearing',0):+.0f} degrees {'visible' if e.get('visible',True) else 'last seen'}" for key,e in enemies.items())
    orders=[list(order) for n in range(1,len(keys)+1) for order in itertools.permutations(keys,n)]
    choices={str(i):order for i,order in enumerate(orders)}
    instructions=('Choose a firing sequence. You may select one target or several in order. '
                  'Keep each target until it disappears from known enemies, then advance to the next listed target. '
                  'A new decision may replace this plan. '
                  f"Latest accepted target: {'#'+str(current) if current is not None else 'none'}. Targets: {facts}.")
    result['questions']['enemy']=dict(type='choice',instructions=instructions,criteria={key:'Shoot '+', then '.join('#'+oid for oid in order)+'.' for key,order in choices.items()})
    result['enemy_sequences']=choices;result['enemy_question_format']=QUESTION_FORMAT
    return result


def validate_sequence(directive):
    if 'target_sequence' not in directive:return
    sequence=directive['target_sequence']
    if directive['action']!='attack' or not isinstance(sequence,list) or not 1<=len(sequence)<=3:raise ValueError('Invalid firing sequence')
    ids=[t['id'] for t in sequence]
    if len(ids)!=len(set(ids)) or (directive.get('target') or {}).get('id')!=ids[0]:raise ValueError('Firing sequence must be unique and start with the selected target')


def advance_sequence(directive,enemies,index=0):
    """Advance monotonically through absent members; never rank or add targets."""
    if 'target_sequence' not in directive:return directive.get('target'),0
    present={e['id'] for e in enemies};sequence=directive['target_sequence']
    while index<len(sequence) and sequence[index]['id'] not in present:index+=1
    return (sequence[index] if index<len(sequence) else None),index


def decode_enemy(packet,key):
    ids=packet['enemy_sequences'][key] if 'enemy_sequences' in packet else [key]
    targets=[copy.deepcopy(packet['targets']['enemy'][oid]) for oid in ids]
    result=dict(target=targets[0])
    if 'enemy_sequences' in packet:result['target_sequence']=targets
    return result
