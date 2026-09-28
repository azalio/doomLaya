"""Learned mechanism scores from observed distances, keys and lift phases."""
import copy
import math
import re

FORMAT = 'laya-switch-numeric-residual-v1'
PROJECTION = 'full-switch-observations-v1'
COLORS = ('red', 'blue', 'yellow')
KINDS = ('lift', 'door', 'floor')
FEATURES = tuple(['key_' + color for color in COLORS] + ['count', 'distance', 'distance_from_nearest'] +
                 ['kind_' + kind for kind in KINDS] + ['phase_' + phase for phase in ('call', 'board', 'ride')] +
                 ['route_' + color for color in COLORS] + ['exit_platform', 'current'] +
                 ['nearest_' + kind for kind in KINDS] + ['missing_' + color for color in COLORS] +
                 ['collected_route_' + color for color in COLORS])


def observations(state, question):
    key_line = re.search(r'^Collected keys: ([^\n]+)', state, re.M)
    if not key_line:
        raise ValueError('Missing collected-key observations')
    keys = set(re.findall(r'\b(red|blue|yellow)\b', key_line[1]))
    current = re.search(r'^Current command: use_switch #([^ ;]+)', state, re.M)
    rows = []
    for key, text in question['criteria'].items():
        distance = re.search(r'\bDistance ([0-9.]+)m\.', text)
        kind = 'lift' if text.startswith('Call, board and ride lift #') else 'door' if text.startswith('Activate door switch #') else 'floor' if text.startswith('Activate floor switch #') else None
        if distance is None or kind is None:
            raise ValueError('Unrecognized observed mechanism')
        phase = re.search(r'\bPhase: (call|board|ride)\.', text)
        route = {color: status for color, status in re.findall(r'\b(red|blue|yellow) \((missing|collected)\)', text)}
        rows.append((key, kind, float(distance[1]), phase[1] if phase else None, route, 'Exit platform.' in text))
    if not rows:
        raise ValueError('Empty mechanism choices')
    minimum = min(row[2] for row in rows)
    nearest_kind = [min((row[2] for row in rows if row[1] == kind), default=256) for kind in KINDS]
    result = []
    for key, kind, distance, phase, route, exit_platform in rows:
        values = [float(color in keys) for color in COLORS] + [len(rows) / 12, distance / 256, (distance - minimum) / 256]
        values += [float(kind == value) for value in KINDS] + [float(phase == value) for value in ('call', 'board', 'ride')]
        values += [float(color in route) for color in COLORS] + [float(exit_platform), float(current is not None and current[1] == key)]
        values += [value / 256 for value in nearest_kind]
        values += [float(route.get(color) == 'missing') for color in COLORS] + [float(route.get(color) == 'collected') for color in COLORS]
        if len(values) != len(FEATURES) or not all(math.isfinite(value) for value in values):
            raise ValueError('Invalid mechanism features')
        result.append(values)
    return result


def make_model(spec):
    import torch
    from torch import nn
    if spec['format'] != FORMAT or spec['input_projection'] != PROJECTION or spec['features'] != list(FEATURES):
        raise ValueError('Mechanism feature schema differs')
    indices, thresholds = [], []
    for key, values in sorted(spec['thresholds'].items(), key=lambda pair: int(pair[0])):
        index = int(key)
        if not 0 <= index < len(FEATURES) or not all(math.isfinite(value) for value in values):
            raise ValueError('Invalid mechanism thresholds')
        indices.extend([index] * len(values))
        thresholds.extend(values)
    hidden = spec['hidden_size']
    if not isinstance(hidden, int) or not 1 <= hidden <= 1024:
        raise ValueError('Invalid mechanism residual width')

    class SwitchResidual(nn.Module):
        def __init__(self):
            super().__init__()
            self.register_buffer('basis_indices', torch.tensor(indices, dtype=torch.long))
            self.register_buffer('basis_thresholds', torch.tensor(thresholds, dtype=torch.float32))
            self.semantic_scale = nn.Parameter(torch.ones(()))
            self.network = nn.Sequential(nn.Linear(len(FEATURES) + len(indices) + 1, hidden), nn.ReLU(),
                                         nn.Linear(hidden, hidden), nn.ReLU(), nn.Linear(hidden, 1))
            nn.init.zeros_(self.network[-1].weight)
            nn.init.zeros_(self.network[-1].bias)

        def forward(self, observed, semantic):
            basis = (observed[..., self.basis_indices] >= self.basis_thresholds).to(observed.dtype)
            inputs = torch.cat([observed, basis, semantic[..., None] / 10], -1)
            return self.semantic_scale * semantic + self.network(inputs).squeeze(-1)

    return SwitchResidual()


def predict(agent, state, questions):
    import torch
    if set(questions) != {'switch'}:
        raise ValueError('Mechanism residual requires one switch question')
    question = questions['switch']
    keys = list(question['criteria'])
    original = agent._semantic_predict(state, questions)
    answer = original['answers']['switch']
    observed = observations(state, question)
    base = [math.log(max(float(answer['probabilities'][key]), agent.numeric_residual_spec['probability_floor'])) for key in keys]
    with torch.no_grad():
        x = torch.tensor([observed], dtype=torch.float32, device=agent.device)
        b = torch.tensor([base], dtype=torch.float32, device=agent.device)
        scores = agent.numeric_residual(x, b)[0]
        probability = scores.cpu().double().softmax(-1).tolist()
        delta = (scores - b[0]).cpu().tolist()
    probabilities = dict(zip(keys, probability))
    choice = max(probabilities, key=probabilities.get)
    result = dict(type='choice', choice=choice, probabilities=probabilities,
                  confidence=probabilities[choice], action=copy.deepcopy(answer.get('action', {})),
                  numeric_residual=dict(composition=FORMAT, semantic_answer=answer,
                                        logit_delta=dict(zip(keys, delta))))
    return dict(original, answers={'switch': result})
