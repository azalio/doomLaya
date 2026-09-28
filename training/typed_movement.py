"""Offline labels: retreat from visible demons, otherwise use lateral movement."""
from doomlib.compact_movement import MOVEMENTS
from doomlib.numeric_movement import features
from doomlib.typed_movement import DEMON_NAMES, typed_features
from training.lateral_movement import choose_lateral


def choose_typed(enemies, clearance, current):
    demons = [enemy for enemy in enemies if enemy.get('visible', True)
              and enemy.get('name') in DEMON_NAMES]
    if demons and min(enemy['distance'] for enemy in demons) < 12 and clearance['back'] >= 4:
        return 'backward'
    return choose_lateral(enemies, clearance, current)


def projected_label(state):
    values = features(state)
    count, distance = typed_features(state)
    current = MOVEMENTS[max(range(4), key=lambda i: values[6 + i])]
    space = dict(zip(('left', 'right', 'back'), [v * 16 for v in values[3:6]]))
    enemies = [dict(name='DoomImp', distance=values[0] * 32)] if values[1] else []
    if count:
        enemies.append(dict(name='Demon', distance=distance * 32))
    return choose_typed(enemies, space, current)
