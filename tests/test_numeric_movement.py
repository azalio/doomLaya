import copy
import importlib.util
import json
import hashlib
import tempfile
from pathlib import Path
from types import SimpleNamespace
import unittest
from doomlib.compact_movement import compact_movement_input, MOVEMENTS
from doomlib.numeric_movement import FORMAT, PROJECTION, FEATURES, features, semantic_logits, make_model, predict


def example():
    packet = json.loads(Path('fixtures/v031-observed-movement-errors.json').read_text())['cases'][0]['packet']
    state, question = compact_movement_input(packet['state'], packet['questions']['movement'])
    return state, question


def spec():
    return dict(format=FORMAT, input_projection=PROJECTION, actions=list(MOVEMENTS), features=list(FEATURES),
                thresholds={'0': [.25, .5], '10': [0.]}, hidden_size=8, probability_floor=.0001)


class MovementFeaturesTests(unittest.TestCase):
    def test_records_exact_clearance_and_current_direction(self):
        state, _ = example()
        values = dict(zip(FEATURES, features(state), strict=True))
        self.assertEqual(values['nearest_under_twelve'], 1)
        self.assertEqual(values['right_at_least_four'], 1)
        self.assertEqual(values['right'], .25)
        self.assertAlmostEqual(values['left_minus_right'], values['left'] - values['right'])

    def test_rejects_incomplete_observations_and_options(self):
        with self.assertRaises(ValueError):
            features('No movement facts')
        with self.assertRaises(ValueError):
            semantic_logits({'probabilities': {'stationary': 1}})

    def test_synthetic_labels_use_the_same_observed_geometry(self):
        from training.finetune_numeric_movement import synthetic
        from training.build_map3_retreat import choose_movement
        for row in synthetic(120, 5):
            f = dict(zip(FEATURES, features(row['state']), strict=True))
            current = MOVEMENTS[[f[k] for k in FEATURES[6:10]].index(1)]
            expected = choose_movement([{'distance': f['nearest'] * 32}],
                                       {side: f[side] * 16 for side in ('left', 'right', 'back')}, current)
            self.assertEqual(row['label'], expected)


@unittest.skipUnless(importlib.util.find_spec('torch'), 'Requires model Python with Torch')
class MovementNetworkTests(unittest.TestCase):
    def test_zero_residual_preserves_semantic_scores(self):
        import torch
        state, _ = example()
        model = make_model(spec())
        semantic = torch.tensor([[1., 2., 3., 4.]])
        self.assertTrue(torch.equal(model(torch.tensor([features(state)]), semantic), semantic))

    def test_trained_weights_choose_direction_and_preserve_semantic_evidence(self):
        import torch
        state, question = example()
        model = make_model(spec())
        with torch.no_grad():
            model.network[-1].bias[2] = 20
        answer = dict(type='choice', choice='stationary', probabilities=dict(zip(MOVEMENTS, [.7, .1, .1, .1])))
        original = dict(model='laya', usage={'input_tokens': 10}, answers={'movement': answer})
        agent = SimpleNamespace(device='cpu', numeric_residual=model, numeric_residual_spec=spec(),
                                _semantic_predict=lambda s,q: copy.deepcopy(original))
        result = predict(agent, state, {'movement': question})
        self.assertEqual(result['answers']['movement']['choice'], 'strafe_right')
        self.assertEqual(result['answers']['movement']['numeric_residual']['semantic_answer'], answer)
        self.assertEqual(set(result['answers']['movement']['probabilities']), set(MOVEMENTS))
        self.assertAlmostEqual(sum(result['answers']['movement']['probabilities'].values()), 1)

    def test_attachment_checks_hashes_format_and_question_kind(self):
        from safetensors.torch import save_file
        from doomlib.numeric_command import attach_numeric_residual
        state, question = example()
        config = spec()
        model = make_model(config)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'numeric-residual.json').write_text(json.dumps(config))
            save_file(model.state_dict(), str(root / 'numeric-residual.safetensors'))
            metadata = dict(format=FORMAT,
                spec_sha256=hashlib.sha256((root / 'numeric-residual.json').read_bytes()).hexdigest(),
                weights_sha256=hashlib.sha256((root / 'numeric-residual.safetensors').read_bytes()).hexdigest())
            answer = dict(type='choice', choice='stationary', probabilities=dict(zip(MOVEMENTS, [.7, .1, .1, .1])))
            agent = SimpleNamespace(device='cpu', cfg={'doom_adaptation': {'input_projection': PROJECTION, 'numeric_residual': metadata}},
                predict=lambda s,q: dict(model='laya', usage={}, answers={'movement': copy.deepcopy(answer)}))
            result = attach_numeric_residual(agent, root)
            self.assertEqual(agent.numeric_residual_question, 'movement')
            self.assertEqual(result['composition'], FORMAT)
            self.assertEqual(agent.predict(state, {'movement': question})['answers']['movement']['choice'], 'stationary')
            metadata['format'] = 'wrong-format'
            with self.assertRaisesRegex(ValueError, 'format'):
                attach_numeric_residual(agent, root)
            metadata['format'] = FORMAT
            (root / 'numeric-residual.safetensors').write_bytes(b'changed')
            with self.assertRaisesRegex(ValueError, 'hash differs'):
                attach_numeric_residual(agent, root)

    def test_schema_and_input_projection_are_verified(self):
        config = spec()
        config['input_projection'] = 'raw'
        with self.assertRaises(ValueError):
            make_model(config)


if __name__ == '__main__':
    unittest.main()
