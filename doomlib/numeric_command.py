"""Observed numeric features and a learned residual on Laya command scores.

No action policy or training labeler is used during inference.
"""
import copy
import hashlib
import json
import math
from pathlib import Path
import re
from doomlib.combat import WEAPON_NAMES, AMMO_COST
from doomlib.command_facts import STABLE_FORMAT

FORMAT = 'laya-command-numeric-residual-v1'
FUSION_FORMAT = 'laya-command-numeric-residual-v2'
FEATURE_FORMAT = 'observed-command-numbers-v1'

ACTIONS = ('attack', 'pickup', 'open_door', 'use_switch', 'exit', 'explore', 'wait', 'retreat')
STATUSES = ('executing', 'blocked', 'unavailable', 'arrived', 'completed', 'inactive')


def item_distances(state):
    result = {}
    for line in state.splitlines():
        if line.startswith('Reachable ') and ' items:' in line:
            for name, distance in re.findall(r'(\w+) ([0-9.]+)m', line):
                result[name] = float(distance)
    return result


def features(row, names):
    state = row['state']
    health = re.search(r'^HP ([0-9.]+); armor ([0-9.]+)', state, re.M)
    inventory = next(line for line in state.splitlines() if line.startswith('Inventory:'))
    ammo = {name: float(count) for name, count in re.findall(r'(\w+) ([0-9.]+) ammo', inventory)}
    values = [float(health[1]) / 100, float(health[2]) / 100]
    for slot, name in WEAPON_NAMES.items():
        values.extend([float(name in ammo), ammo.get(name, 0) / 100, float(name in ammo and ammo[name] >= AMMO_COST[slot])])
    for mode in ('visible', 'last seen'):
        match = re.search(mode + r' count (\d+)(?:, nearest ([0-9.]+)m)?', state)
        values.extend([int(match[1]) / 3, min(float(match[2] or 256), 256) / 32])
    mechanisms = re.search(r'Available mechanisms: (\d+); exit platforms: (\d+)', state)
    values.extend([int(mechanisms[1]) / 10, int(mechanisms[2])])
    command = re.search(r'^Current command: (\w+)(?: #([^ ;]+))?', state, re.M)
    status = re.search(r'^Current command: .*?; status (\w+)', state, re.M)
    values.extend(float(command is not None and command[1] == action) for action in ACTIONS)
    values.extend(float(status is not None and status[1] == candidate) for candidate in STATUSES)
    current_lift = None
    for match in re.finditer(r'#(\d+) phase (board|ride) ([0-9.]+)m', state):
        if command and command[1] == 'use_switch' and command[2] == match[1]:
            current_lift = match
    if current_lift is None:
        current_lift = re.search(r'Selected lift in progress: #(\d+) phase (board|ride) ([0-9.]+)m', state)
    values.extend([float(current_lift is not None), min(float(current_lift[3]) if current_lift else 256, 256) / 32])
    door = re.search(r'A closed door is ([0-9.]+) meters away', state)
    values.extend([float(door is not None), min(float(door[1]) if door else 256, 256) / 32, float('A closed door blocks movement' in state)])
    keys = next(line for line in state.splitlines() if line.startswith('Collected keys:'))
    values.extend(float(color in keys) for color in ('red', 'blue', 'yellow'))
    items = item_distances(state)
    for name in names:
        values.extend([float(name in items), min(items.get(name, 256), 256) / 32])
    values.extend(float(action in row['question']['criteria']) for action in ACTIONS)
    return values


def feature_names(names):
    result = ['health', 'armor']
    for name in WEAPON_NAMES.values():
        result += [name + suffix for suffix in ('_owned', '_ammo', '_loaded')]
    for mode in ('visible', 'recent'):
        result += [mode + '_enemies', mode + '_enemy_distance']
    result += ['mechanisms', 'exit_platforms']
    result += ['current_' + name for name in ACTIONS]
    result += ['status_' + name for name in STATUSES]
    result += ['selected_lift_present', 'selected_lift_distance', 'door_present', 'door_distance', 'door_blocks_motion']
    result += ['key_' + color for color in ('red', 'blue', 'yellow')]
    for name in names:
        result += ['item_' + name + '_present', 'item_' + name + '_distance']
    result += ['available_' + name for name in ACTIONS]
    return result


def semantic_logits(answer, floor=0.0001):
    return [math.log(max(float(answer['probabilities'].get(action, 0)), floor)) for action in ACTIONS]


def make_residual_model(spec):
    import torch
    from torch import nn
    if spec['format'] not in (FORMAT, FUSION_FORMAT) or spec['feature_format'] != FEATURE_FORMAT or spec['input_projection'] != STABLE_FORMAT:
        raise ValueError('Unsupported numeric residual format')
    if spec['actions'] != list(ACTIONS) or spec['feature_names'] != feature_names(spec['item_names']):
        raise ValueError('Numeric feature/action schema differs')
    indices, thresholds = [], []
    for key, values in sorted(spec['thresholds'].items(), key=lambda pair: int(pair[0])):
        index = int(key)
        if not 0 <= index < len(spec['feature_names']) or not all(math.isfinite(float(v)) for v in values):
            raise ValueError('Invalid learned observation thresholds')
        indices.extend([index] * len(values)); thresholds.extend(values)
    width = len(spec['feature_names']) + len(indices) + len(ACTIONS)
    hidden = spec['hidden_size']
    if not isinstance(hidden, int) or not 1 <= hidden <= 1024:
        raise ValueError('Invalid residual network width')

    class NumericResidual(nn.Module):
        def __init__(self):
            super().__init__()
            self.register_buffer('basis_indices', torch.tensor(indices, dtype=torch.long))
            self.register_buffer('basis_thresholds', torch.tensor(thresholds, dtype=torch.float32))
            if spec['format'] == FUSION_FORMAT:
                self.semantic_scale = nn.Parameter(torch.ones(()))
            self.network = nn.Sequential(nn.Linear(width, hidden), nn.ReLU(), nn.Linear(hidden, hidden), nn.ReLU(), nn.Linear(hidden, len(ACTIONS)))
            nn.init.zeros_(self.network[-1].weight)
            nn.init.zeros_(self.network[-1].bias)

        def forward(self, observed, semantic):
            basis = (observed[:, self.basis_indices] >= self.basis_thresholds).to(observed.dtype)
            inputs = torch.cat([observed, basis, semantic / 10], dim=-1)
            return semantic * getattr(self, 'semantic_scale', 1.0) + self.network(inputs)

    return NumericResidual()


def predict_with_numeric_residual(agent, state, questions):
    import torch
    if set(questions) != {'command'}:
        raise ValueError('Numeric command residual only supports the command question')
    question = questions['command']
    if question.get('type') != 'choice' or not question.get('criteria') or set(question['criteria']) - set(ACTIONS):
        raise ValueError('Numeric command residual requires explicit known action choices')
    original = agent._semantic_predict(state, questions)
    semantic_answer = original['answers']['command']
    spec = agent.numeric_residual_spec
    observed = features(dict(state=state, question=question), spec['item_names'])
    if len(observed) != len(spec['feature_names']) or not all(math.isfinite(value) for value in observed):
        raise ValueError('Invalid observed numerical features')
    base = semantic_logits(semantic_answer, spec['probability_floor'])
    with torch.no_grad():
        x = torch.tensor([observed], dtype=torch.float32, device=agent.device)
        b = torch.tensor([base], dtype=torch.float32, device=agent.device)
        logits = agent.numeric_residual(x, b)[0]
        allowed = torch.tensor([action in question['criteria'] for action in ACTIONS], device=agent.device)
        p = logits.masked_fill(~allowed, -float('inf')).cpu().double().softmax(-1).tolist()
        delta = (logits - b[0]).cpu().tolist()
    probabilities = {key: p[ACTIONS.index(key)] for key in question['criteria']}
    choice = max(probabilities, key=probabilities.get)
    answer = dict(type='choice', choice=choice, probabilities=probabilities, confidence=probabilities[choice],
        action=copy.deepcopy(semantic_answer.get('action', {})),
        numeric_residual=dict(composition=spec['format'], semantic_answer=semantic_answer,
            logit_delta={key: delta[ACTIONS.index(key)] for key in question['criteria']}))
    return dict(original, answers={'command': answer})


def attach_numeric_residual(agent, root):
    from safetensors.torch import load_file
    from types import MethodType
    root = Path(root)
    metadata = agent.cfg.get('doom_adaptation', {}).get('numeric_residual')
    if not metadata:
        return None
    expected = {'numeric-residual.json': metadata['spec_sha256'], 'numeric-residual.safetensors': metadata['weights_sha256']}
    for filename, digest in expected.items():
        if hashlib.sha256((root / filename).read_bytes()).hexdigest() != digest:
            raise ValueError('Numeric residual artifact hash differs: ' + filename)
    spec = json.loads((root / 'numeric-residual.json').read_text())
    from doomlib.numeric_item import FORMAT as ITEM_FORMAT, make_model as make_item_model, predict as predict_item
    from doomlib.compact_item import CATEGORY_FORMAT
    from doomlib.numeric_movement import FORMAT as MOVEMENT_FORMAT, PROJECTION as MOVEMENT_PROJECTION, make_model as make_movement_model, predict as predict_movement
    from doomlib.numeric_movement import TYPED_FORMAT as TYPED_MOVEMENT_FORMAT
    from doomlib.typed_movement import PROJECTION as TYPED_MOVEMENT_PROJECTION
    from doomlib.numeric_switch import FORMAT as SWITCH_FORMAT, PROJECTION as SWITCH_PROJECTION, make_model as make_switch_model, predict as predict_switch
    from doomlib.numeric_enemy import FORMAT as ENEMY_FORMAT, PROJECTION as ENEMY_PROJECTION, make_model as make_enemy_model, predict as predict_enemy
    formats = {
        FORMAT: ('command', STABLE_FORMAT, make_residual_model, predict_with_numeric_residual),
        FUSION_FORMAT: ('command', STABLE_FORMAT, make_residual_model, predict_with_numeric_residual),
        ITEM_FORMAT: ('item', CATEGORY_FORMAT, make_item_model, predict_item),
        MOVEMENT_FORMAT: ('movement', MOVEMENT_PROJECTION, make_movement_model, predict_movement),
        TYPED_MOVEMENT_FORMAT: ('movement', TYPED_MOVEMENT_PROJECTION, make_movement_model, predict_movement),
        SWITCH_FORMAT: ('switch', SWITCH_PROJECTION, make_switch_model, predict_switch),
        ENEMY_FORMAT: ('enemy', ENEMY_PROJECTION, make_enemy_model, predict_enemy),
    }
    if metadata['format'] != spec['format'] or spec['format'] not in formats:
        raise ValueError('Numeric residual format differs or is unsupported')
    question, expected_projection, factory, predictor = formats[spec['format']]
    if agent.cfg['doom_adaptation'].get('input_projection') != expected_projection:
        raise ValueError('Numeric residual and input projection differ')
    agent.numeric_residual_question = question
    model = factory(spec)
    model.load_state_dict(load_file(str(root / 'numeric-residual.safetensors')), strict=True)
    model.to(agent.device).eval()
    for parameter in model.parameters():
        parameter.requires_grad_(False)
    agent.numeric_residual = model
    agent.numeric_residual_spec = spec
    agent._semantic_predict = agent.predict
    agent.predict = MethodType(predictor, agent)
    return dict(composition=spec['format'], numeric_residual_weights_sha256=metadata['weights_sha256'],
                numeric_residual_spec_sha256=metadata['spec_sha256'])
