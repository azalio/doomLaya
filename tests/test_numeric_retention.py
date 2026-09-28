import json
from pathlib import Path
import unittest

from training.finetune_numeric_retention import all_keys_observed


class RetentionBoundaryTests(unittest.TestCase):
    def test_completed_key_states_are_not_negative_retention_examples(self):
        cases = json.loads(Path('fixtures/v031-finish-route-cases.json').read_text())['cases']
        for case in cases:
            self.assertNotIn('keys', case['packet']['observation'])
            self.assertTrue(all_keys_observed(case['packet']))

    def test_partial_keys_stay_in_retention_and_missing_observation_fails(self):
        self.assertFalse(all_keys_observed({'state': 'Collected keys: blue, yellow.'}))
        self.assertFalse(all_keys_observed({'state': 'Collected keys: none.'}))
        self.assertTrue(all_keys_observed({'state': 'Collected keys: yellow, red, blue.'}))
        with self.assertRaises(ValueError):
            all_keys_observed({'state': 'No collected-key observation'})
