import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from training.build_map3_continuation import build


class ContinuationSplitTests(unittest.TestCase):
    def test_late_holdout_excludes_same_input_from_training_and_keeps_replay(self):
        def decision(seconds, state):
            return dict(game_seconds=seconds, tick=int(seconds * 35), episode=7, packet=dict(
                state=state, observation=dict(hp=40, inventory={}, execution={}),
                targets=dict(switch={'721': dict(kind='door', distance=5)}),
                questions=dict(command=dict(type='choice', instructions='Choose',
                    criteria=dict(pickup='Item', use_switch='Switch')))))
        def replay_row(state):
            return dict(kind='command', label='use_switch', category='old', state=state,
                question=dict(type='choice', instructions='Choose', criteria=dict(pickup='Item', use_switch='Switch')))
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); run = root / 'run'; old = root / 'old'; out = root / 'out'
            run.mkdir(); old.mkdir()
            # 960 belongs to a validation block, 980 to training. The first two
            # states are identical after the same runtime goal projection.
            rows = [decision(960, 'Current command: pickup #540\nCollected keys: blue, yellow.'),
                    decision(980, 'Current command: use_switch #721\nCollected keys: blue, yellow.'),
                    decision(1000, 'HP 39\nCollected keys: blue, yellow.')]
            (run / 'decisions.jsonl').write_text('\n'.join(json.dumps(r) for r in rows))
            (old / 'train.json').write_text(json.dumps([replay_row('old train')]))
            (old / 'validation.json').write_text(json.dumps([replay_row('old validation')]))
            with contextlib.redirect_stdout(io.StringIO()):
                build(run, old, out)
            train = json.loads((out / 'train.json').read_text())
            valid = json.loads((out / 'validation.json').read_text())
            train_states = {r['state'] for r in train}; valid_states = {r['state'] for r in valid}
            self.assertFalse(train_states & valid_states)
            self.assertIn('Collected keys: blue, yellow.', valid_states)
            self.assertNotIn('Collected keys: blue, yellow.', train_states)
            self.assertIn('HP 39\nCollected keys: blue, yellow.', train_states)
            self.assertIn('old train', train_states)
            self.assertIn('old validation', valid_states)
            self.assertEqual({r['label'] for r in train + valid}, {'use_switch'})


if __name__ == '__main__':
    unittest.main()
