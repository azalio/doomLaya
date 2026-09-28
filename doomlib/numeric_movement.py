"""Learned movement residual from observed geometry and frozen Laya scores."""
import copy
import math
import re
from doomlib.compact_movement import FORMAT as PROJECTION, MOVEMENTS

FORMAT = 'laya-movement-numeric-residual-v1'
TYPED_FORMAT = 'laya-movement-numeric-residual-v2-enemy-type'
FEATURES = ('nearest', 'known', 'visible', 'left', 'right', 'back',
            'current_stationary', 'current_left', 'current_right', 'current_back', 'left_minus_right',
            'nearest_under_twelve', 'left_at_least_two', 'left_at_least_four',
            'right_at_least_two', 'right_at_least_four', 'back_at_least_two', 'back_at_least_four')
TYPED_FEATURES = FEATURES + ('visible_demons', 'nearest_visible_demon')


def features(state, typed=False):
    counts = re.search(r'Known enemies: (\d+); visible enemies: (\d+)', state)
    nearest = re.search(r'Nearest visible threat, or remembered threat if none visible: ([0-9.]+) meters', state)
    current = re.search(r'Current movement: (\w+)', state)
    space = {side: re.search(r'Body clearance ' + side + r': ([0-9.]+) meters', state)
             for side in ('left', 'right', 'back')}
    if not counts or not nearest or not current or current[1] not in MOVEMENTS or not all(space.values()):
        raise ValueError('Incomplete observed movement geometry')
    distances = {side: float(match[1]) for side, match in space.items()}
    values = [float(nearest[1]) / 32, int(counts[1]) / 10, int(counts[2]) / 10]
    values += [distances[side] / 16 for side in ('left', 'right', 'back')]
    values += [float(current[1] == movement) for movement in MOVEMENTS]
    values += [(distances['left'] - distances['right']) / 16]
    near_band = re.search(r'This threat is closer than twelve meters: (yes|no)\.', state)
    bands = [re.search(r'Body clearance ' + side + r': [0-9.]+ meters\. At least two meters: (yes|no)\. At least four meters: (yes|no)\.', state) for side in ('left', 'right', 'back')]
    if not near_band or not all(bands):
        raise ValueError('Missing factual movement distance bands')
    values.append(float(near_band[1] == 'yes'))
    for band in bands:
        values.extend([float(band[1] == 'yes'), float(band[2] == 'yes')])
    if typed:
        from doomlib.typed_movement import typed_features
        values.extend(typed_features(state))
    if not all(math.isfinite(value) for value in values):
        raise ValueError('Non-finite movement observation')
    return values


def semantic_logits(answer, floor=0.0001):
    if set(answer['probabilities']) != set(MOVEMENTS):
        raise ValueError('Movement options differ')
    return [math.log(max(float(answer['probabilities'][key]), floor)) for key in MOVEMENTS]


def make_model(spec):
    import torch
    from torch import nn
    from doomlib.typed_movement import PROJECTION as TYPED_PROJECTION
    schemas = {FORMAT: (PROJECTION, FEATURES), TYPED_FORMAT: (TYPED_PROJECTION, TYPED_FEATURES)}
    projection, feature_names = schemas.get(spec['format'], (None, ()))
    if (spec['format'] not in schemas or spec['input_projection'] != projection or spec['actions'] != list(MOVEMENTS)
            or spec['features'] != list(feature_names)):
        raise ValueError('Invalid movement residual schema')
    indices, thresholds = [], []
    for key, values in sorted(spec['thresholds'].items(), key=lambda item: int(item[0])):
        index = int(key)
        if not 0 <= index < len(feature_names) or not all(math.isfinite(float(v)) for v in values):
            raise ValueError('Invalid movement basis')
        indices.extend([index] * len(values))
        thresholds.extend(values)
    hidden = spec['hidden_size']
    if not isinstance(hidden, int) or not 1 <= hidden <= 1024:
        raise ValueError('Invalid movement network width')

    class MovementResidual(nn.Module):
        def __init__(self):
            super().__init__()
            self.register_buffer('basis_indices', torch.tensor(indices, dtype=torch.long))
            self.register_buffer('basis_thresholds', torch.tensor(thresholds, dtype=torch.float32))
            self.semantic_scale = nn.Parameter(torch.ones(()))
            width = len(feature_names) + len(indices) + len(MOVEMENTS)
            self.network = nn.Sequential(nn.Linear(width, hidden), nn.ReLU(), nn.Linear(hidden, hidden),
                                         nn.ReLU(), nn.Linear(hidden, len(MOVEMENTS)))
            nn.init.zeros_(self.network[-1].weight)
            nn.init.zeros_(self.network[-1].bias)

        def forward(self, observed, semantic):
            basis = (observed[:, self.basis_indices] >= self.basis_thresholds).to(observed.dtype)
            inputs = torch.cat([observed, basis, semantic / 10], dim=-1)
            return semantic * self.semantic_scale + self.network(inputs)

    return MovementResidual()


def predict(agent, state, questions):
    import torch
    if set(questions) != {'movement'} or set(questions['movement']['criteria']) != set(MOVEMENTS):
        raise ValueError('Numeric movement requires all four explicit movements')
    typed = agent.numeric_residual_spec['format'] == TYPED_FORMAT
    from doomlib.typed_movement import semantic_state
    original = agent._semantic_predict(semantic_state(state) if typed else state, questions)
    answer = original['answers']['movement']
    base = semantic_logits(answer, agent.numeric_residual_spec['probability_floor'])
    with torch.no_grad():
        x = torch.tensor([features(state, typed)], dtype=torch.float32, device=agent.device)
        b = torch.tensor([base], dtype=torch.float32, device=agent.device)
        scores = agent.numeric_residual(x, b)[0]
        probabilities = dict(zip(MOVEMENTS, scores.cpu().double().softmax(-1).tolist()))
        delta = dict(zip(MOVEMENTS, (scores - b[0]).cpu().tolist()))
    choice = max(probabilities, key=probabilities.get)
    result = dict(type='choice', choice=choice, probabilities=probabilities, confidence=probabilities[choice],
                  action=copy.deepcopy(answer.get('action', {})), numeric_residual=dict(composition=agent.numeric_residual_spec['format'],
                  semantic_answer=answer, logit_delta=delta))
    return dict(original, answers={'movement': result})
