import unittest
from training.lateral_movement import choose_lateral, projected_label
from training.finetune_numeric_movement import synthetic


class LateralMovementTests(unittest.TestCase):
    def test_open_lateral_space_precedes_retreat(self):
        self.assertEqual(choose_lateral([dict(distance=1.5)], dict(left=4, right=1, back=8), 'backward'), 'strafe_left')

    def test_keep_safe_side_to_avoid_alternation(self):
        self.assertEqual(choose_lateral([dict(distance=5)], dict(left=2, right=8, back=8), 'strafe_left'), 'strafe_left')
        self.assertEqual(choose_lateral([dict(distance=5)], dict(left=1.75, right=8, back=8), 'strafe_left'), 'strafe_right')

    def test_blocked_sides_keep_retreat_and_stationary_available(self):
        self.assertEqual(choose_lateral([dict(distance=5)], dict(left=1, right=1, back=4), 'stationary'), 'backward')
        self.assertEqual(choose_lateral([dict(distance=15)], dict(left=1, right=1, back=4), 'stationary'), 'stationary')
        self.assertEqual(choose_lateral([], dict(left=4, right=4, back=4), 'stationary'), 'stationary')

    def test_generated_labels_match_projected_facts(self):
        for row in synthetic(100, 884, choose_lateral):
            self.assertEqual(row['label'], projected_label(row['state']))


if __name__ == '__main__':
    unittest.main()
