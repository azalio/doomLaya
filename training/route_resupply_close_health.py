"""Offline resupply correction: a nearby fight outranks a longer healing detour."""
from training.route_resupply import labels as resupply_labels


def labels(packet):
    result = resupply_labels(packet)
    if not result or result[0][2] != 'route_urgent_health':
        return result
    item = next(value for kind, value, _ in result if kind == 'item')
    distance = packet['targets']['item'][item]['distance']
    enemies = packet.get('targets', {}).get('enemy', {}).values()
    if distance >= 2 and any(enemy['distance'] < 20 for enemy in enemies) and 'attack' in packet['questions']['command']['criteria']:
        return [('command', 'attack', 'route_fight')]
    return result
