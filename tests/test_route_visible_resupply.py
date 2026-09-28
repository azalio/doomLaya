import copy
import json
from pathlib import Path
import unittest
from tests import test_route_resupply as resupply
from training.route_resupply_close_health import labels as old_labels
from training.route_visible_resupply import labels
from training.numeric_augmentation import examples


class VisibleResupplyTests(unittest.TestCase):
    def packet(self, name='Shell', category='Ammo'):
        packet = resupply.ResupplyLabelsTests().packet(name, category)
        packet['targets']['enemy'] = {'e': dict(distance=30, visible=True)}
        packet['questions']['command']['criteria']['attack'] = 'Fight'
        return packet

    def test_visible_enemy_at_range_does_not_lose_to_ammo(self):
        packet = self.packet()
        original = copy.deepcopy(packet)
        self.assertEqual(old_labels(packet)[0][1], 'pickup')
        self.assertEqual(labels(packet)[0][1], 'attack')
        self.assertEqual(packet, original)
        packet['targets']['enemy']['e']['visible'] = False
        self.assertEqual(labels(packet)[0][1], 'pickup')

    def test_close_emergency_health_and_first_gun_remain_available(self):
        packet = self.packet('Medikit', 'Health')
        packet['observation']['hp'] = 20
        packet['targets']['item']['1']['distance'] = 1.5
        self.assertEqual(labels(packet)[0][1], 'pickup')
        packet['observation']['hp'] = 30
        self.assertEqual(labels(packet)[0][1], 'attack')
        packet = self.packet('Shotgun', 'Weapon')
        packet['observation']['inventory']['3']['owned'] = 0
        packet['targets']['item']['1']['distance'] = 4
        self.assertEqual(labels(packet)[0][1], 'pickup')
        packet['targets']['item']['1']['distance'] = 7
        self.assertEqual(labels(packet)[0][1], 'attack')

    def test_recorded_distractions_are_relabelled_without_changing_observations(self):
        cases = json.loads(Path('fixtures/v031-visible-fight-cases.json').read_text())['cases']
        self.assertEqual(len(cases), 12)
        for case in cases:
            packet = copy.deepcopy(case['packet'])
            self.assertNotEqual(case['recorded_command'], 'attack')
            self.assertEqual(labels(packet)[0][1], 'attack')
            self.assertEqual(packet, case['packet'])

    def test_seeded_augmentation_uses_only_available_choices(self):
        names = {'Medikit': 'Health', 'Shotgun': 'Weapon', 'BlueCard': 'Key', 'Clip': 'Ammo'}
        for row in examples(names, 200, 42, labels, include_items=True, broad_inventory=True):
            self.assertIn(row['label'], row['question']['criteria'])


if __name__ == '__main__':
    unittest.main()
