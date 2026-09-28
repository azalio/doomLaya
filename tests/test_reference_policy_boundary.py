"""A reference-policy rollout must never pass the model-authority gate."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from tools.check_authority import check


class ReferencePolicyBoundaryTest(unittest.TestCase):
    def test_reference_config_or_response_rejects_an_otherwise_valid_motor_trace(self):
        config = dict(protocol='model-authority-v1', args=dict(dry=False, give='', record=False), source_sha256={})
        summary = dict(errors=0, status='completed', levels_completed=0, final_map='MAP01', video_frames=1)
        directive = dict(decision_id=1, action='wait', target=None, weapon=None, expires_tick=10)
        decision = dict(packet=dict(commands={'wait': dict(action='wait', target=None)}, weapons={}),
            directive=directive, answers={'command': {'choice': 'wait'}, 'weapon': {'choice': 'keep'}},
            applied=True, episode=0, game_seconds=0, tick=0, routing={})
        row = dict(tick=0, buttons=[0] * 14, execution=dict(decision_id=1, action='wait', target_id=None),
            episode=0, seconds=0, enemies=[], weapon=2)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / 'summary.json').write_text(json.dumps(summary))
            (root / 'telemetry.jsonl').write_text(json.dumps(row) + '\n')
            for mode in ('real_model', 'reference_config', 'reference_response'):
                c, d = copy.deepcopy(config), copy.deepcopy(decision)
                if mode == 'reference_config':
                    c['laya_health'] = {'diagnostic_policy': 'offline-reference'}
                if mode == 'reference_response':
                    d['routing']['diagnostic_policy'] = 'offline-reference'
                (root / 'config.json').write_text(json.dumps(c))
                (root / 'decisions.jsonl').write_text(json.dumps(d) + '\n')
                result = check(root)
                self.assertEqual(result['pass'], mode == 'real_model', result)
                if mode != 'real_model':
                    self.assertTrue(any('Diagnostic reference' in error for error in result['errors']))


if __name__ == '__main__':
    unittest.main()
