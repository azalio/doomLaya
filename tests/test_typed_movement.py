import copy
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import unittest
from doomlib.compact_movement import compact_movement_input, MOVEMENTS
from doomlib.typed_movement import PROJECTION, typed_movement_input, semantic_state, typed_features
from doomlib.numeric_movement import TYPED_FORMAT, TYPED_FEATURES, features, make_model, predict
from training.typed_movement import choose_typed, projected_label


def packet():
    return json.loads(Path('fixtures/v031-lateral-movement-cases.json').read_text())['cases'][6]['packet']


class TypedMovementFactsTests(unittest.TestCase):
    def test_frozen_text_input_and_options_are_unchanged(self):
        p = packet()
        old, question = compact_movement_input(p['state'], p['questions']['movement'])
        new, projected = typed_movement_input(p['state'], p['questions']['movement'])
        self.assertEqual(semantic_state(new), old)
        self.assertEqual(projected, question)
        self.assertEqual(features(new, True)[:-2], features(old))
        self.assertEqual(typed_features(new), [0, 8])

    def test_remembered_demons_do_not_become_visible_threats(self):
        p = packet()
        state = '\n'.join(line for line in p['state'].splitlines() if not line.startswith('Enemies:'))
        state += '\nEnemies: Demon#1 0.5m (last seen); Spectre#2 5.0m (visible); DoomImp#3 1.0m (visible).'
        new, _ = typed_movement_input(state, p['questions']['movement'])
        self.assertEqual(typed_features(new), [.1, 5 / 32])
        with self.assertRaises(ValueError):
            typed_features(semantic_state(new))

    def test_retreat_needs_visible_demon_and_room_behind(self):
        space = dict(left=5, right=7, back=6)
        self.assertEqual(choose_typed([dict(name='Demon', distance=3)], space, 'strafe_left'), 'backward')
        self.assertEqual(choose_typed([dict(name='DoomImp', distance=3)], space, 'strafe_left'), 'strafe_left')
        self.assertEqual(choose_typed([dict(name='Demon', distance=3, visible=False)], space, 'strafe_left'), 'strafe_left')
        self.assertEqual(choose_typed([dict(name='Demon', distance=3)], dict(space, back=1), 'strafe_left'), 'strafe_left')

    def test_synthetic_labels_match_only_projected_observations(self):
        from training.finetune_numeric_movement import synthetic
        group = synthetic(200, 981, choose_typed, True)
        self.assertEqual(group, synthetic(200, 981, choose_typed, True))
        for row in group:
            self.assertEqual(row['label'], projected_label(row['state']))


@unittest.skipUnless(importlib.util.find_spec('torch'), 'Requires model Python with Torch')
class TypedMovementRuntimeTests(unittest.TestCase):
    def test_runtime_uses_learned_weights_and_original_text_branch(self):
        import torch
        from doomlib.question_heads import QuestionHeads
        p = packet()
        config = dict(format=TYPED_FORMAT, input_projection=PROJECTION, features=list(TYPED_FEATURES),
                      actions=list(MOVEMENTS), thresholds={'19': [.25]}, hidden_size=8, probability_floor=.0001)
        model = make_model(config)
        with torch.no_grad():
            model.network[-1].bias[3] = 20
        original, _ = compact_movement_input(p['state'], p['questions']['movement'])
        semantic_calls = []
        def semantic(state, questions):
            semantic_calls.append(state)
            return dict(model='laya', usage={}, answers={'movement': dict(type='choice', choice='stationary',
                        probabilities=dict(zip(MOVEMENTS, [.7, .1, .1, .1])))})
        agent = SimpleNamespace(device='cpu', numeric_residual=model, numeric_residual_spec=config,
            cfg={'doom_adaptation': {'input_projection': PROJECTION}}, _semantic_predict=semantic)
        agent.predict = lambda state, questions: predict(agent, state, questions)
        result = QuestionHeads(agent, {'movement': agent}, movement_compact_facts=True).predict(
            p['state'], {'movement': p['questions']['movement']})
        self.assertEqual(result['answers']['movement']['choice'], 'backward')
        self.assertEqual(result['answers']['movement']['numeric_residual']['composition'], TYPED_FORMAT)
        self.assertEqual(semantic_calls, [original])


if __name__ == '__main__':
    unittest.main()
