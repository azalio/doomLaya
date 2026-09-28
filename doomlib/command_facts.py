"""Compact observed command facts; never score, remove or choose an action."""
import collections
import copy
import re

from doomlib.combat import AMMO_COST, WEAPON_NAMES
from doomlib.items import WEAPONS

FORMAT = 'command-observed-facts-v1'


def command_facts_input(state, question):
    lines = state.splitlines()
    def single(prefix, required=False):
        matches = [line for line in lines if line.startswith(prefix)]
        if len(matches) > 1 or (required and not matches):
            raise ValueError('Missing or ambiguous command observation: ' + prefix)
        return matches[0] if matches else None
    hp = single('HP ', True)
    inventory_line = single('Inventory:', True)
    keys = single('Collected keys:', True)
    reachable = single('Reachable items:', True)
    inventory = {name: float(ammo) for name, ammo in re.findall(r'(\w+) ([0-9.]+) ammo', inventory_line)}
    if not inventory:
        raise ValueError('Missing owned-weapon observations')
    loaded = [name for slot, name in WEAPON_NAMES.items() if AMMO_COST[slot] > 0 and name in inventory and inventory[name] >= AMMO_COST[slot]]
    output = [hp, inventory_line, 'Loaded ranged weapons: ' + (', '.join(loaded) or 'none') + '.', keys]

    enemy_line = single('Enemies:')
    enemies = re.findall(r'\w+#[^\s]+ ([0-9.]+)m \((visible|last seen)\)', enemy_line or '')
    if enemy_line and not enemies:
        raise ValueError('Unrecognized enemy observations')
    parts = []
    for mode in ('visible', 'last seen'):
        distances = [float(distance) for distance, observed in enemies if observed == mode]
        parts.append(f'{mode} count {len(distances)}' + (f', nearest {min(distances):.1f}m' if distances else ''))
    output.append('Enemies: ' + '; '.join(parts) + '.')

    mechanisms = single('Available mechanisms:')
    entries = mechanisms.removeprefix('Available mechanisms:').strip().split('; ') if mechanisms else []
    if any(not re.match(r'(?:lift|door switch|floor switch) #\d+', entry) for entry in entries):
        raise ValueError('Unrecognized mechanism observations')
    output.append(f'Available mechanisms: {len(entries)}; exit platforms: {sum("Exit platform." in entry for entry in entries)}.')
    lifts = []
    for entry in entries:
        match = re.match(r'lift #(\d+) phase (\w+) ([0-9.]+)m', entry)
        if match and match[2] in ('board', 'ride'):
            lifts.append(f'#{match[1]} phase {match[2]} {match[3]}m')
    output.append('Boarding or riding lifts: ' + ('; '.join(lifts) or 'none') + '.')
    for prefix in ('Current command:', 'Previous command result:', 'A closed door ', 'Door requires ', 'Route blocked:'):
        fact = single(prefix)
        if fact:
            output.append(fact)

    available = set(re.findall(r'(\w+)#([^\s,;.]+)', reachable))
    nearest = {}
    for name, key, category, distance in re.findall(r'(\w+)#([^\s,;.]+) \[(\w+)\] ([0-9.]+)m', single('Items:') or ''):
        if (name, key) not in available:
            continue
        group = (category, name)
        nearest[group] = min(float(distance), nearest.get(group, float('inf')))
    groups = collections.defaultdict(list)
    for (category, name), distance in sorted(nearest.items()):
        fact = f'{name} {distance:.1f}m'
        if category == 'Weapon':
            slot = WEAPONS.get(name)
            if slot is None:
                raise ValueError('Unknown observed weapon: ' + name)
            weapon = WEAPON_NAMES[slot]
            fact += f', owned {"yes" if weapon in inventory else "no"}'
            if weapon in inventory:
                fact += f', ammo {inventory[weapon]:g}'
        groups[category].append(fact)
    for category in ('Key', 'Health', 'Weapon', 'Armor', 'Ammo', 'Powerup'):
        output.append('Reachable ' + category + ' items: ' + ('; '.join(groups.pop(category, [])) or 'none') + '.')
    if groups:
        raise ValueError('Unknown observed item category')
    return '\n'.join(output), copy.deepcopy(question)


STABLE_FORMAT = 'command-observed-facts-v2-lift-context'


def stable_command_facts_input(state, question):
    """Keep physical lift execution context, omit the generic previous action."""
    selected, result = command_facts_input(state, question)
    current = re.search(r'^Current command: use_switch #(\d+)\b', state, re.M)
    lifts = next(line for line in selected.splitlines() if line.startswith('Boarding or riding lifts:'))
    active = None
    if current:
        active = re.search(r'#' + re.escape(current[1]) + r' phase (board|ride) ([0-9.]+)m', lifts)
    context = ('#' + current[1] + ' phase ' + active[1] + ' ' + active[2] + 'm') if active else 'none'
    lines = [line for line in selected.splitlines() if not line.startswith('Current command:')]
    lines.insert(lines.index(lifts) + 1, 'Selected lift in progress: ' + context + '.')
    return '\n'.join(lines), result


BINNED_FORMAT = 'command-observed-facts-v3-bands'


def observed_band(value, boundaries):
    """A physical measurement interval, without action scores or preferences."""
    value = float(value)
    lower = 0
    for upper in boundaries:
        if value < upper:
            return f'[{lower},{upper})'
        lower = upper
    return f'[{lower},infinity)'


def binned_command_facts_input(state, question):
    """Represent command measurements as intervals; all action choices remain."""
    selected, result = stable_command_facts_input(state, question)
    selected = re.sub(r'^HP ([0-9.]+); armor ([0-9.]+)\.',
        lambda m: 'HP band ' + observed_band(m[1], (35, 45, 75)) + '; armor band ' + observed_band(m[2], (60,)) + '.', selected, flags=re.M)
    selected = re.sub(r'([0-9.]+) ammo', lambda m: 'ammo band ' + observed_band(m[1], (1, 2, 4, 15)), selected)
    selected = re.sub(r', ammo ([0-9.]+)', lambda m: ', ammo band ' + observed_band(m[1], (1, 2, 4, 15)), selected)
    selected = re.sub(r'([0-9.]+)(m\b| meters\b)',
        lambda m: 'distance band ' + observed_band(m[1], (3, 4, 5, 6, 8, 10, 20)) + ' meters', selected)
    return selected, result
