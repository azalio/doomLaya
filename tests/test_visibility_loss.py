import importlib.util
import unittest
from training.build_enemy_visibility import synthetic


@unittest.skipUnless(importlib.util.find_spec('torch'), 'Requires model Python with Torch')
class VisibilityLossTests(unittest.TestCase):
    def test_only_visible_subset_receives_the_positive_target_gradient(self):
        import torch
        from training.ranking import visible_first_loss
        row = next(synthetic(1, 101))
        values = list(row['question']['criteria'].values())
        logits = torch.zeros(1, len(values), requires_grad=True)
        loss = visible_first_loss(logits, [row], {'mixed_visibility_synthetic'})
        loss.backward()
        for i, text in enumerate(values):
            if '; visible;' in text:
                self.assertLess(logits.grad[0, i], 0)
            elif '; last seen;' in text:
                self.assertGreater(logits.grad[0, i], 0)
            else:
                self.assertEqual(logits.grad[0, i], 0)

    def test_original_replay_is_not_given_auxiliary_labels(self):
        import torch
        from training.ranking import visible_first_loss
        row = next(synthetic(1, 101))
        row['category'] = 'full_3'
        logits = torch.randn(1, len(row['question']['criteria']), requires_grad=True)
        loss = visible_first_loss(logits, [row], {'mixed_visibility_synthetic'})
        loss.backward()
        self.assertEqual(float(loss.detach()), 0)
        self.assertEqual(float(logits.grad.abs().sum()), 0)

    def test_invalid_observations_are_rejected(self):
        import torch
        from training.ranking import visible_first_loss
        row = next(synthetic(1, 101))
        key = next(iter(row['question']['criteria']))
        row['question']['criteria'][key] = 'guessed target facts'
        with self.assertRaisesRegex(ValueError, 'observed ranking facts'):
            visible_first_loss(torch.zeros(1, len(row['question']['criteria'])), [row], {'mixed_visibility_synthetic'})
