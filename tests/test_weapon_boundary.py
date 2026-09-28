import unittest
from training.build_weapon_boundary import synthetic, weapon_label, row_for


class WeaponBoundaryTests(unittest.TestCase):
    def test_one_shell_cannot_load_super_shotgun(self):
        cases = [(p, i, c) for p, i, c in synthetic('train')
                 if p['observation']['inventory']['8']['ammo'] == 1]
        self.assertTrue(cases)
        choices = set()
        for packet, _, _ in cases:
            label = weapon_label(packet)
            self.assertNotEqual(label, 'super_shotgun')
            self.assertIn('Loaded: no.', packet['questions']['weapon']['criteria']['super_shotgun'])
            choices.add(label)
        self.assertEqual(choices, {'melee', 'pistol', 'shotgun', 'chaingun'})

    def test_two_shells_enable_super_shotgun(self):
        for packet, _, _ in synthetic('validation'):
            if packet['observation']['inventory']['8']['ammo'] == 2:
                self.assertEqual(weapon_label(packet), 'super_shotgun')
                self.assertIn('Loaded: yes.', packet['questions']['weapon']['criteria']['super_shotgun'])

    def test_projected_row_keeps_actual_question_and_raw_observation(self):
        packet, index, category = next(synthetic('train'))
        row = row_for(packet, category=category)
        self.assertEqual(row['question'], packet['questions']['weapon'])
        self.assertEqual(row['raw_state'], packet['state'])
        self.assertEqual(row['label'], weapon_label(packet))


if __name__ == '__main__':
    unittest.main()
