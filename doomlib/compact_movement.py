"""Compact observed combat geometry for a separately trained movement head."""
import copy, math, re
FORMAT = 'movement-compact-v1'
MOVEMENTS = ('stationary', 'strafe_left', 'strafe_right', 'backward')
INSTRUCTIONS = 'Choose movement while fighting. Use observed enemy distance, body clearance and current movement to stay alive while aiming and firing.'


def movement_facts(state, question):
    if set(question['criteria']) != set(MOVEMENTS): raise ValueError('Compact movement requires four explicit directions')
    current = re.search(r'Movement: ([^.]+)', state)
    if not current or current[1] not in MOVEMENTS: raise ValueError('Missing current movement')
    enemy_line = next((line for line in state.splitlines() if line.startswith('Enemies:')), '')
    enemies = re.findall(r'#[^ ;]+ ([0-9.]+)m(?: \((visible|last seen)\))?', enemy_line)
    if not enemies: raise ValueError('Missing observed enemies')
    visible = [float(distance) for distance, status in enemies if status != 'last seen']
    known = [float(distance) for distance, _ in enemies]
    clearance = {}
    for key, side in [('strafe_left','left'), ('strafe_right','right'), ('backward','back')]:
        value = re.search(r'Body clearance in this direction: ([0-9.]+)m', question['criteria'][key])
        if not value: raise ValueError('Missing measured clearance: ' + side)
        clearance[side] = float(value[1])
    if any(not math.isfinite(value) or value < 0 for value in known + list(clearance.values())):
        raise ValueError('Invalid observed distance')
    return dict(nearest=min(visible or known), known_enemies=len(known), visible_enemies=len(visible), current=current[1], clearance=clearance)


def compact_movement_input(state, question):
    facts = movement_facts(state, question)
    lines = [f"Known enemies: {facts['known_enemies']}; visible enemies: {facts['visible_enemies']}.",
             f"Nearest visible threat, or remembered threat if none visible: {facts['nearest']:.2f} meters.",
             'This threat is closer than twelve meters: ' + ('yes.' if facts['nearest'] < 12 else 'no.'),
             f"Current movement: {facts['current']}."]
    for side, distance in facts['clearance'].items():
        lines.append(f"Body clearance {side}: {distance:.2f} meters. At least two meters: {'yes' if distance >= 2 else 'no'}. At least four meters: {'yes' if distance >= 4 else 'no'}.")
    result = copy.deepcopy(question); result['instructions'] = INSTRUCTIONS
    return '\n'.join(lines), result
