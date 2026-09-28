import copy
import json
from pathlib import Path
import unittest
from training.route_resupply import labels as old_labels
from training.route_resupply_close_health import labels


class CloseHealthLabelsTests(unittest.TestCase):
    def cases(self):
        return json.loads(Path('fixtures/v031-close-health-regression-cases.json').read_text())['cases']

    def test_recorded_melee_threat_outranks_distant_health(self):
        self.assertGreaterEqual(len(self.cases()), 4)
        for case in self.cases():
            packet = case['packet']
            before = copy.deepcopy(packet)
            self.assertEqual(old_labels(packet)[0][1], 'pickup')
            self.assertEqual(labels(packet), [('command', 'attack', 'route_fight')])
            self.assertEqual(packet, before)

    def test_nearly_reached_health_remains_urgent(self):
        packet = self.cases()[0]['packet']
        chosen = next(v for k,v,_ in old_labels(packet) if k == 'item')
        packet['targets']['item'][chosen]['distance'] = 1.5
        self.assertEqual(labels(packet), old_labels(packet))
        self.assertEqual(labels(packet)[0][1], 'pickup')

    def test_no_threat_does_not_interrupt_healing(self):
        packet = self.cases()[0]['packet']
        packet['targets']['enemy'] = {}
        self.assertEqual(labels(packet), old_labels(packet))
        self.assertEqual(labels(packet)[0][1], 'pickup')
