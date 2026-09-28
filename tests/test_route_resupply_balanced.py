import copy
import json
from pathlib import Path
import unittest
from training.route_resupply import labels as previous_labels
from training.route_resupply_balanced import labels


class BalancedResourceTests(unittest.TestCase):
    def test_recorded_key_detours_preserve_command_and_prefer_helpful_supply(self):
        cases = json.loads(Path('fixtures/v031-balanced-resupply.json').read_text())['cases']
        self.assertEqual(len(cases), 8)
        for case in cases:
            with self.subTest(tick=case['tick']):
                packet = case['packet']
                before = copy.deepcopy(packet)
                previous = previous_labels(packet)
                actual = labels(packet)
                self.assertEqual(previous[0], actual[0])
                self.assertEqual(actual, [tuple(row) for row in case['expected_labels']])
                self.assertNotEqual(previous, actual)
                self.assertEqual(packet, before)
                selected = next(v for k,v,_ in actual if k == 'item')
                self.assertEqual(packet['targets']['item'][selected]['category'], 'Health')

    def test_full_health_keeps_the_key(self):
        case = json.loads(Path('fixtures/v031-balanced-resupply.json').read_text())['cases'][0]
        packet = case['packet']
        packet['observation']['hp'] = 100
        packet['observation']['armor'] = 100
        packet['targets']['item'] = {k:v for k,v in packet['targets']['item'].items()
                                   if v['category'] in ('Health', 'Key')}
        actual = labels(packet)
        selected = next(v for k,v,_ in actual if k == 'item')
        self.assertEqual(packet['targets']['item'][selected]['category'], 'Key')
