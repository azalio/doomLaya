"""Offline survival-oriented revision of route labels; never a live controller."""
from doomlib.combat import AMMO_COST
from training.route_priority import labels as route_labels


def labels(packet):
    result=route_labels(packet)
    command=next((r for r in result if r[0]=='command'),None)
    if command is None or command[2]!='route_close_weapon':return result
    inventory=packet['observation']['inventory']
    loaded=any(int(slot) not in (1,9) and entry['owned'] and entry['ammo']>=AMMO_COST[int(slot)] for slot,entry in inventory.items())
    threat=any(enemy.get('visible',True) or enemy['distance']<20 for enemy in packet.get('targets',{}).get('enemy',{}).values())
    if loaded and threat and 'attack' in packet['questions']['command']['criteria']:
        return [('command','attack','route_finish_fight_before_upgrade')]
    return result
