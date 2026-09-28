import unittest
from diagnostics.probe_regression_cases import check


class RegressionProbeTests(unittest.TestCase):
    def test_enemy_first_checks_the_decoded_sequence(self):
        case=dict(check='expected_enemy_first',expected_enemy='1',
                  packet={'enemy_sequences':{'a':['1','2'],'b':['2','1']}})
        self.assertTrue(check(case,{'enemy':{'choice':'a'}}))
        self.assertFalse(check(case,{'enemy':{'choice':'b'}}))

    def test_isolated_movement_and_switch_checks_do_not_require_a_command(self):
        for kind, expected in [('movement', 'strafe_right'), ('switch', '662'), ('weapon', 'shotgun')]:
            case = dict(check='expected_' + kind, **{'expected_' + kind: expected})
            self.assertTrue(check(case, {kind: {'choice': expected}}))
            self.assertFalse(check(case, {kind: {'choice': 'other'}}))


if __name__ == '__main__':
    unittest.main()
