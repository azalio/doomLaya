import copy
import json
from pathlib import Path
import unittest
from training.build_collected_key_switches import correction


class CollectedKeySwitchTests(unittest.TestCase):
    def packet(self):
        return json.loads(Path('fixtures/v031-collected-key-switch-v2-cases.json').read_text())['cases'][0]['packet']

    def test_recorded_returns_to_collected_key_have_an_offered_alternative(self):
        cases = json.loads(Path('fixtures/v031-collected-key-switch-v2-cases.json').read_text())['cases']
        self.assertEqual(len(cases), 12)
        for case in cases:
            before = copy.deepcopy(case['packet'])
            self.assertEqual(correction(before), case['expected_switch'])
            self.assertNotEqual(case['recorded_switch'], case['expected_switch'])
            self.assertIn(case['expected_switch'], before['questions']['switch']['criteria'])
            self.assertEqual(before, case['packet'])

    def test_a_missing_key_is_not_marked_completed(self):
        packet = self.packet()
        packet['state'] = packet['state'].replace('Collected keys: blue.', 'Collected keys: none.')
        self.assertIsNone(correction(packet))

    def test_preserves_boarding_or_riding_a_selected_nearby_lift(self):
        packet = self.packet()
        key = next(k for k,v in packet['targets']['switch'].items() if v.get('route_keys'))
        for phase in ('board', 'ride'):
            packet['targets']['switch'][key].update(kind='lift', phase=phase, distance=2)
            packet['observation']['execution'] = dict(action='use_switch', target_id=key)
            self.assertIsNone(correction(packet))


if __name__ == '__main__':
    unittest.main()
