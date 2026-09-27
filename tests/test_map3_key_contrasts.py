import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from training.build_map3_key_contrasts import build


class KeyContrastTests(unittest.TestCase):
    def test_contrasts_keep_shared_ammo_and_holdout_source_separate(self):
        question = dict(type='choice', instructions='Choose', criteria=dict(pickup='Item', use_switch='Mechanism'))
        rows = [dict(kind='command', label='pickup', category='mechanics_route_pickup',
                     state=f'Reachable items: RedCard#27, Stimpack#34.\nHP 101; armor 100.\nInventory: pistol 120 ammo; shotgun 20 ammo; chaingun 120 ammo.\nItems: RedCard#27 [Key] {distance}m.',
                     question=question, source_run='map03-mechanics-exit-platform54', source_tick=tick)
                for tick, distance in ((3700, 4.9), (3718, 4.6), (3736, 1.2))]
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / 'source'; output = Path(tmp) / 'output'; source.mkdir()
            (source / 'train.json').write_text(json.dumps(rows))
            (source / 'validation.json').write_text('[]')
            with contextlib.redirect_stdout(io.StringIO()):
                build(source, output)
            train = json.loads((output / 'train.json').read_text())
            valid = json.loads((output / 'validation.json').read_text())
            self.assertNotIn(3736, {r['source_tick'] for r in train})
            self.assertEqual({r['source_tick'] for r in valid}, {3736})
            self.assertFalse({r['state'] for r in train} & {r['state'] for r in valid})
            for row in train + valid:
                self.assertEqual(row['question'], question)
                self.assertEqual(row['label'], 'pickup')
                if not row.get('synthetic'):
                    continue
                values = row['counterfactual']
                self.assertIn(f"pistol {values['bullets']} ammo", row['state'])
                self.assertIn(f"chaingun {values['bullets']} ammo", row['state'])
                self.assertIn(f"shotgun {values['shells']} ammo", row['state'])
                self.assertGreaterEqual(values['hp'], 85)
                self.assertGreaterEqual(values['shells'], 20)
                self.assertGreaterEqual(values['bullets'], 100)
                self.assertIn('Reachable items: RedCard#' + values['key_identifier'], row['state'])


if __name__ == '__main__':
    unittest.main()
