"""Learned target-ranking scores over observed geometry and the previous target."""
import copy
import math
import re

from doomlib.enemy_ranking import FORMAT as PROJECTION, STOP

FORMAT = 'laya-enemy-numeric-residual-v1'
NAMES = ('ShotgunGuy', 'Zombieman', 'ChaingunGuy', 'DoomImp', 'Demon', 'Spectre', 'Cacodemon', 'HellKnight', 'BaronOfHell', 'Revenant', 'LostSoul')
FEATURES = ('stop', 'visible', 'previous', 'distance', 'bearing', 'absolute_bearing',
            'count', 'visible_count', 'nearest_distance', 'nearest_visible_distance',
            'distance_from_nearest', 'distance_from_nearest_visible',
            'visible_previous_present', 'previous_distance') + tuple('type_' + name for name in NAMES) + ('type_other',)


def observations(state, question):
    rows = []
    for key, text in question['criteria'].items():
        if key == STOP:
            continue
        match = re.fullmatch(r'(\w+); distance ([0-9.]+)m; bearing ([+-]?[0-9]+) degrees; (visible|last seen); latest accepted target: (yes|no)\.', text)
        if not match:
            raise ValueError('Unrecognized observed target facts')
        name, distance, bearing, visible, previous = match.groups()
        rows.append(dict(key=key, name=name, distance=float(distance), bearing=float(bearing),
                         visible=visible == 'visible', previous=previous == 'yes'))
    if not 1 <= len(rows) <= 3 or STOP not in question['criteria'] or sum(r['previous'] for r in rows) > 1:
        raise ValueError('Invalid target-ranking choices')
    nearest = min(r['distance'] for r in rows)
    visible = [r for r in rows if r['visible']]
    nearest_visible = min((r['distance'] for r in visible), default=256)
    prior = next((r for r in rows if r['previous']), None)
    by_key = {r['key']: r for r in rows}
    result = []
    for key in question['criteria']:
        r = by_key.get(key)
        values = ([0., float(r['visible']), float(r['previous']), r['distance']/32,
                   r['bearing']/180, abs(r['bearing'])/180] if r else [1., 0., 0., 0., 0., 0.])
        values += [len(rows)/3, len(visible)/3, nearest/32, nearest_visible/32,
                   (r['distance']-nearest)/32 if r else 0.,
                   (r['distance']-nearest_visible)/32 if r else 0.,
                   float(prior is not None and prior['visible']), prior['distance']/32 if prior else 8.]
        values += [float(r is not None and r['name'] == name) for name in NAMES]
        values += [float(r is not None and r['name'] not in NAMES)]
        if len(values) != len(FEATURES) or not all(math.isfinite(value) for value in values):
            raise ValueError('Invalid target-ranking geometry')
        result.append(values)
    return result


def make_model(spec):
    import torch
    from torch import nn
    if spec['format'] != FORMAT or spec['input_projection'] != PROJECTION or spec['features'] != list(FEATURES):
        raise ValueError('Target-ranking feature schema differs')
    indices, thresholds = [], []
    for key, values in sorted(spec['thresholds'].items(), key=lambda pair: int(pair[0])):
        index = int(key)
        if not 0 <= index < len(FEATURES) or not all(math.isfinite(value) for value in values):
            raise ValueError('Invalid target-ranking thresholds')
        indices.extend([index] * len(values)); thresholds.extend(values)
    hidden = spec['hidden_size']
    if not isinstance(hidden, int) or not 1 <= hidden <= 1024:
        raise ValueError('Invalid target-ranking network width')

    class EnemyResidual(nn.Module):
        def __init__(self):
            super().__init__()
            self.register_buffer('basis_indices', torch.tensor(indices, dtype=torch.long))
            self.register_buffer('basis_thresholds', torch.tensor(thresholds, dtype=torch.float32))
            self.semantic_scale = nn.Parameter(torch.ones(()))
            self.network = nn.Sequential(nn.Linear(len(FEATURES)+len(indices)+1, hidden), nn.ReLU(),
                                         nn.Linear(hidden, hidden), nn.ReLU(), nn.Linear(hidden, 1))
            nn.init.zeros_(self.network[-1].weight); nn.init.zeros_(self.network[-1].bias)

        def forward(self, observed, semantic):
            basis = (observed[..., self.basis_indices] >= self.basis_thresholds).to(observed.dtype)
            inputs = torch.cat([observed, basis, semantic[..., None]/10], -1)
            return self.semantic_scale * semantic + self.network(inputs).squeeze(-1)

    return EnemyResidual()


def predict(agent, state, questions):
    import torch
    if set(questions) != {'enemy'}:
        raise ValueError('Target-ranking residual requires one enemy question')
    question = questions['enemy']; keys = list(question['criteria'])
    original = agent._semantic_predict(state, questions); answer = original['answers']['enemy']
    base = [math.log(max(float(answer['probabilities'][key]), agent.numeric_residual_spec['probability_floor'])) for key in keys]
    with torch.no_grad():
        x = torch.tensor([observations(state, question)], dtype=torch.float32, device=agent.device)
        b = torch.tensor([base], dtype=torch.float32, device=agent.device)
        scores = agent.numeric_residual(x, b)[0]
        probabilities = dict(zip(keys, scores.cpu().double().softmax(-1).tolist()))
        delta = dict(zip(keys, (scores-b[0]).cpu().tolist()))
    choice = max(probabilities, key=probabilities.get)
    result = dict(type='choice', choice=choice, probabilities=probabilities, confidence=probabilities[choice],
                  action=copy.deepcopy(answer.get('action', {})),
                  numeric_residual=dict(composition=FORMAT, semantic_answer=answer, logit_delta=delta))
    return dict(original, answers={'enemy': result})
