"""Offline labels: finish an unlocked level before optional distant resupply."""
import re

from doomlib.combat import AMMO_COST
from training.route_visible_resupply import labels as visible_labels


def labels(packet):
    result = visible_labels(packet)
    if not result or result[0][2] != 'route_needed_supply':
        return result
    collected = re.search(r'^Collected keys: ([^\n]+)', packet['state'], re.M)
    keys = set(re.findall(r'\b(red|blue|yellow)\b', collected[1])) if collected else set()
    observation = packet['observation']
    inventory = observation['inventory']
    armed = any(inventory.get(str(slot), {}).get('owned') and
                inventory[str(slot)]['ammo'] >= AMMO_COST[slot] for slot in (3, 4, 6, 8))
    selected = next(value for kind, value, _ in result if kind == 'item')
    item = packet['targets']['item'][selected]
    if keys != {'red', 'blue', 'yellow'} or observation['hp'] < 45 or not armed or item['distance'] <= 6:
        return result
    options = packet['questions']['command']['criteria']
    mechanisms = packet.get('targets', {}).get('switch', {}).values()
    if 'use_switch' in options and any(m.get('route_exit') and not m.get('activated') for m in mechanisms):
        return [('command', 'use_switch', 'route_finish_platform')]
    if 'exit' in options:
        return [('command', 'exit', 'route_finish_exit')]
    return result
