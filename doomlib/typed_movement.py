"""Add observed Demon/Spectre geometry to the movement model input."""
import math
import re
from doomlib.compact_movement import compact_movement_input

PROJECTION = 'movement-compact-v2-enemy-type'
PREFIX = 'Visible Demon or Spectre observations: '
DEMON_NAMES = frozenset(('Demon', 'Spectre'))


def demon_observations(state):
    line = next((line for line in state.splitlines() if line.startswith('Enemies:')), '')
    found = re.findall(r'(\w+)#[^\s;]+ ([0-9.]+)m(?: \((visible|last seen)\))?', line)
    distances = [float(distance) for name, distance, status in found
                 if name in DEMON_NAMES and status != 'last seen']
    if not all(math.isfinite(value) and value >= 0 for value in distances):
        raise ValueError('Invalid observed demon distance')
    return len(distances), min(distances, default=256.0)


def typed_movement_input(state, question):
    projected, result = compact_movement_input(state, question)
    count, nearest = demon_observations(state)
    return projected + f'\n{PREFIX}count {count}; nearest {nearest:.2f} meters.', result


def semantic_state(state):
    """Keep the frozen text branch byte-identical to its original v1 input."""
    return '\n'.join(line for line in state.splitlines() if not line.startswith(PREFIX))


def typed_features(state):
    match = re.search(re.escape(PREFIX) + r'count (\d+); nearest ([0-9.]+) meters\.', state)
    if not match:
        raise ValueError('Missing observed enemy-type geometry')
    count, nearest = int(match[1]), float(match[2])
    if not math.isfinite(nearest) or nearest < 0 or (count == 0 and nearest != 256):
        raise ValueError('Invalid observed enemy-type geometry')
    return [count / 10, min(nearest, 256) / 32]
