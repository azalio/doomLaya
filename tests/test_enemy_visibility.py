import unittest
from training.build_enemy_visibility import example, synthetic
from doomlib.enemy_ranking import STOP


class EnemyVisibilityTests(unittest.TestCase):
    def test_replay_checks_the_first_enemy_in_the_selected_sequence(self):
        from diagnostics.probe_regression_cases import check
        case = dict(check='visible_enemy_first', expected_visible_targets=['2'],
                    packet={'enemy_sequences': {'a': ['1', '2'], 'b': ['2', '1']}})
        self.assertFalse(check(case, {'enemy': {'choice': 'a'}}))
        self.assertTrue(check(case, {'enemy': {'choice': 'b'}}))

    def test_nearby_remembered_enemy_does_not_displace_a_visible_target(self):
        packet = dict(state='HP 74; armor 4.\nInventory: shotgun 22 ammo.',
                      questions={'enemy': {}}, enemy_commitment={'target_id': '1'},
                      targets={'enemy': {
                          '1': dict(id=1, name='Zombieman', distance=.5, bearing=0, visible=False),
                          '2': dict(id=2, name='ShotgunGuy', distance=12., bearing=30, visible=True)}})
        row = example(packet, {'category': 'test'})
        self.assertEqual(row['target_ranking'], ['2', '1', STOP])
        self.assertEqual(set(row['question']['criteria']), {'1', '2', STOP})

    def test_synthetic_inputs_preserve_visibility_and_reproducibility(self):
        rows = list(synthetic(40, 100))
        self.assertEqual(rows, list(synthetic(40, 100)))
        self.assertNotEqual(rows, list(synthetic(40, 101)))
        for row in rows:
            self.assertIn('; visible;', row['question']['criteria'][row['label']])
            self.assertTrue(any('; last seen;' in text for text in row['question']['criteria'].values()))
            self.assertEqual(set(row['target_ranking']), set(row['question']['criteria']))
