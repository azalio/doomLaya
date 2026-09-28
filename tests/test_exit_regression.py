import copy
import unittest
from training.build_exit_regression import completed_mechanisms


class ExitRegressionTests(unittest.TestCase):
    def test_completed_mechanism_contrast_preserves_other_world_facts(self):
        row=dict(kind='command',label='use_switch',category='correction_route_continue_route',state='Available mechanisms: door switch #8 4.0m\nHP 80; armor 50.\nInventory: pistol 40 ammo.\nCollected keys: red.\nItems: Medikit#2 [Health] 8.0m.',question=dict(type='choice',instructions='Finish the level alive.',criteria=dict(use_switch='Mechanism',exit='Exit',pickup='Supply')),source_run='a',source_tick=10)
        original=copy.deepcopy(row);result=completed_mechanisms(row)
        self.assertEqual(row,original)
        self.assertEqual(result['label'],'exit')
        self.assertEqual(result['state'],'\n'.join(original['state'].splitlines()[1:]))
        self.assertEqual(set(result['question']['criteria']),{'exit','pickup'})
        self.assertEqual((result['source_run'],result['source_tick']),('a',10))
        self.assertTrue(result['synthetic'])

    def test_does_not_interrupt_an_active_lift_or_exit_platform(self):
        for category in ('correction_route_continue_lift','correction_route_exit_platform'):
            row=dict(label='use_switch',category=category,question=dict(criteria=dict(exit='Exit',use_switch='Use')))
            self.assertIsNone(completed_mechanisms(row))

    def test_does_not_invent_unavailable_exit(self):
        row=dict(label='use_switch',category='correction_route_continue_route',question=dict(criteria=dict(use_switch='Use')))
        self.assertIsNone(completed_mechanisms(row))


if __name__=='__main__':unittest.main()
