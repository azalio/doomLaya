import copy
import json
from pathlib import Path
import unittest

from training.route_finish import labels
from training.route_visible_resupply import labels as prior_labels
from training.numeric_augmentation import examples


class FinishRouteTests(unittest.TestCase):
    def setUp(self):
        self.cases = json.loads(Path('fixtures/v031-finish-route-cases.json').read_text())['cases']

    def test_recorded_supply_loop_prefers_exit_mechanism_without_mutation(self):
        self.assertEqual(len(self.cases), 16)
        for case in self.cases:
            packet = copy.deepcopy(case['packet'])
            self.assertEqual(prior_labels(packet)[0][1], 'pickup')
            self.assertEqual(labels(packet)[0][1], case['expected_command'])
            self.assertEqual(packet, case['packet'])

    def test_nearby_supply_incomplete_keys_and_low_health_remain_available(self):
        for condition in ('nearby', 'key_missing', 'low_health', 'unarmed'):
            packet = copy.deepcopy(self.cases[0]['packet'])
            if condition == 'nearby':
                selected = next(value for kind, value, _ in prior_labels(packet) if kind == 'item')
                packet['targets']['item'][selected]['distance'] = 4
            elif condition == 'key_missing':
                packet['state'] = packet['state'].replace('Collected keys: blue, red, yellow.', 'Collected keys: blue, red.')
            elif condition == 'low_health':
                packet['observation']['hp'] = 30
            else:
                for slot in (3, 4, 6, 8):
                    packet['observation']['inventory'][str(slot)]['ammo'] = 0
            with self.subTest(condition=condition):
                self.assertEqual(labels(packet)[0][1], 'pickup')

    def test_fight_priority_and_exit_after_activation(self):
        packet = copy.deepcopy(self.cases[0]['packet'])
        for mechanism in packet['targets']['switch'].values():
            if mechanism.get('route_exit'):
                mechanism['activated'] = True
        self.assertEqual(labels(packet)[0][1], 'exit')
        packet['questions']['command']['criteria']['attack'] = 'Fight'
        packet['targets']['enemy'] = {'e': dict(distance=30, visible=True)}
        self.assertEqual(labels(packet)[0][1], 'attack')

    def test_seeded_augmentation_never_selects_unavailable_action(self):
        names = {'Medikit': 'Health', 'Shotgun': 'Weapon', 'BlueCard': 'Key', 'Clip': 'Ammo'}
        for row in examples(names, 300, 42, labels, broad_inventory=True, broad_mechanisms=True):
            self.assertIn(row['label'], row['question']['criteria'])


if __name__ == '__main__':
    unittest.main()
