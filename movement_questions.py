"""Attach measured body clearance without selecting or removing movements."""
import copy
import math
import re


def describe_movement(question,clearance,current_movement=None):
    for side in ('left','right','back'):
        value=clearance.get(side)
        if not isinstance(value,(int,float)) or isinstance(value,bool) or not math.isfinite(value) or value<0:
            raise ValueError('Missing or invalid body clearance: '+side)
    question=copy.deepcopy(question)
    question['instructions']+=' Use body clearance to avoid blocked directions, including when continuing the previous movement.'
    for choice in question['criteria']:
        movement=current_movement if choice=='continue' else choice
        side={'strafe_left':'left','strafe_right':'right','backward':'back'}.get(movement)
        if side:question['criteria'][choice]+=f' Body clearance in this direction: {clearance[side]:.2f}m.'
    return question


def with_movement_clearance(packet,clearance):
    if 'movement' not in packet['questions']:return packet
    packet['questions']['movement']=describe_movement(packet['questions']['movement'],clearance,packet.get('current_movement'))
    packet['movement_clearance']=dict(clearance)
    return packet


def without_movement_continuation(packet):
    if 'movement' in packet['questions']:
        packet['questions']['movement']['criteria'].pop('continue',None)
    return packet


def explicit_example(row):
    result=copy.deepcopy(row)
    if result['kind']!='movement':return result
    if result['label']=='continue':
        match=re.search(r'Movement: ([^.]+)',result['state'])
        if not match or match[1] not in result['question']['criteria']:
            raise ValueError('Movement continuation has no explicit equivalent')
        result['label']=match[1]
    without_movement_continuation({'questions':{'movement':result['question']}})
    return result
