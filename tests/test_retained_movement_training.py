import unittest
from training.build_map3_retained_movement import choose_retained


class RetainedMovementTrainingTest(unittest.TestCase):
    def test_recorded_yellow_key_reversal_is_not_repeated(self):
        self.assertEqual(choose_retained([dict(distance=7.7)],dict(left=6.5,right=3.25,back=1.5),'strafe_right'),'strafe_right')

    def test_backward_priority_is_preserved(self):
        self.assertEqual(choose_retained([dict(distance=7.8)],dict(left=4.5,right=.5,back=9.5),'strafe_left'),'backward')

    def test_blocked_side_is_not_retained(self):
        self.assertEqual(choose_retained([dict(distance=7)],dict(left=1.75,right=3,back=5),'strafe_left'),'backward')
        self.assertEqual(choose_retained([dict(distance=7)],dict(left=2,right=3,back=1),'strafe_left'),'strafe_left')

    def test_retreat_ends_when_threat_is_far_or_path_blocked(self):
        self.assertEqual(choose_retained([dict(distance=7)],dict(left=1,right=1,back=2),'backward'),'stationary')
        self.assertEqual(choose_retained([dict(distance=14)],dict(left=3,right=1,back=8),'backward'),'strafe_left')
        self.assertEqual(choose_retained([],dict(left=3,right=1,back=8),'backward'),'stationary')
