"""Release metadata may be sanitized; source and decision records must stay exact."""
import json
from pathlib import Path
import tempfile
import unittest

from scripts.package_regression_evidence import public_bytes


class RegressionEvidencePackageTest(unittest.TestCase):
    def test_metadata_removes_local_paths_but_preserves_measurements(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'config.json'
            path.write_text(json.dumps({'script': '/' + 'Users' + '/fixture/game.py',
                                        'seed': 48, 'minimum_decision_delay_ticks': 0}))
            self.assertEqual(json.loads(public_bytes(path)),
                             {'script': 'game.py', 'seed': 48, 'minimum_decision_delay_ticks': 0})

    def test_clean_jsonl_stays_byte_identical(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'decisions.jsonl'
            data = b'{ "tick": 105, "command": "exit" }\n'
            path.write_bytes(data)
            self.assertEqual(public_bytes(path), data)

    def test_private_paths_in_records_are_rejected_not_rewritten(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'decisions.jsonl'
            path.write_text(json.dumps({'path': '/' + 'Users' + '/fixture/private'}))
            with self.assertRaisesRegex(ValueError, 'Private path in non-metadata'):
                public_bytes(path)

    def test_secret_in_metadata_is_rejected_before_sanitizing(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'config.json'
            path.write_text(json.dumps({'token': 'sk-or-' + 'v1-' + 'x' * 30}))
            with self.assertRaisesRegex(ValueError, 'Secret pattern'):
                public_bytes(path)
