"""Offline lateral-first movement labels, supported by recorded combat branches."""
from doomlib.compact_movement import MOVEMENTS
from doomlib.numeric_movement import features


def choose_lateral(enemies, clearance, current):
    candidates = [e for e in enemies if e.get('visible', True)] or enemies
    if not candidates:
        return 'stationary'
    side = {'strafe_left': 'left', 'strafe_right': 'right'}.get(current)
    if side is None or clearance[side] < 2:
        side = max(('left', 'right'), key=lambda key: clearance[key])
    if clearance[side] >= 2:
        return 'strafe_' + side
    if min(e['distance'] for e in candidates) < 12 and clearance['back'] >= 4:
        return 'backward'
    return 'stationary'


def projected_label(state):
    values = features(state)
    current = MOVEMENTS[max(range(4), key=lambda i: values[6 + i])]
    space = dict(zip(('left', 'right', 'back'), [v * 16 for v in values[3:6]]))
    enemies = [dict(distance=values[0] * 32)] if values[1] else []
    return choose_lateral(enemies, space, current)
