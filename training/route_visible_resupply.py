"""Offline command labels: retain visible fights with close health/weapon exceptions."""
from doomlib.combat import AMMO_COST
from doomlib.items import WEAPONS
from training.route_resupply_close_health import labels as close_labels


def labels(packet):
    result = close_labels(packet)
    targets = packet.get('targets', {})
    enemies = list(targets.get('enemy', {}).values())
    nearest = min((enemy['distance'] for enemy in enemies), default=float('inf'))
    if ('attack' not in packet['questions']['command']['criteria'] or
            not (any(enemy.get('visible', True) for enemy in enemies) or nearest < 20)):
        return result
    observation = packet['observation']
    inventory = observation['inventory']
    usable = {int(key) for key, value in inventory.items()
              if value['owned'] and value['ammo'] >= AMMO_COST[int(key)]}
    slot = next(key for key in (6, 8, 4, 3, 2, 5, 9, 1) if key in usable)
    items = [(key, item) for key, item in targets.get('item', {}).items() if item.get('reachable')]
    hp = observation['hp']
    urgent = [(220 - 2 * item['distance'], key, item) for key, item in items
              if item['category'] == 'Health' and 'Bonus' not in item['name']
              and hp < 35 and item['distance'] < 6]
    upgrades = [(180 - 2 * item['distance'], key, item) for key, item in items
                if item['category'] == 'Weapon' and WEAPONS.get(item['name']) in (3, 4, 6, 8)
                and not inventory.get(str(WEAPONS[item['name']]), {}).get('owned')
                and slot in (1, 2) and item['distance'] < 10]
    current = observation.get('execution') or {}
    blocked = ('open_door' in packet['questions']['command']['criteria'] and
               'A closed door blocks movement' in current.get('detail', ''))
    riding = any(value.get('kind') == 'lift' and value.get('phase') in ('board', 'ride')
                 and value['distance'] < 5 and current.get('action') == 'use_switch'
                 and str(current.get('target_id')) == key
                 for key, value in targets.get('switch', {}).items())
    health_exception = bool(not blocked and not riding and urgent and
                            max(urgent)[2]['distance'] < 2 and hp < 25)
    upgrade_exception = bool(not blocked and not riding and not urgent and upgrades
                             and nearest >= 3 and max(upgrades)[2]['distance'] < 6 and nearest > 3)
    if health_exception or upgrade_exception:
        chosen = max(urgent if health_exception else upgrades)[1]
        return [('command', 'pickup', 'route_close_fight_supply'),
                ('item', chosen, 'route_health' if health_exception else 'route_weapon')]
    return [('command', 'attack', 'route_visible_fight' if any(
        enemy.get('visible', True) for enemy in enemies) else 'route_fight')]
