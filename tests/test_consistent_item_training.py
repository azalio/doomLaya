"""The item replay must learn corrections and exclude the next map episode."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from training.build_consistent_command import build


class ConsistentItemTrainingTest(unittest.TestCase):
    def test_failed_choices_are_relabelled_without_next_map_leakage(self):
        cases = json.loads(Path('fixtures/v031-item-regression-cases.json').read_text())['cases'][-6:]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run = root / 'source-run'
            run.mkdir()
            (run / 'config.json').write_text(json.dumps({'args': {'map': 'MAP01'}}))
            (run / 'summary.json').write_text(json.dumps({'levels_completed': 1, 'deaths': 0}))
            records = []
            for tick, episode, case in ((700, 0, cases[0]), (0, 0, cases[1]), (701, 1, cases[2])):
                records.append(dict(tick=tick, episode=episode, packet=copy.deepcopy(case['packet']),
                    answers={'item': {'choice': '30'}}))
            (run / 'decisions.jsonl').write_text(''.join(json.dumps(record) + '\n' for record in records))
            fixture = root / 'cases.json'
            fixture.write_text(json.dumps({'cases': []}))
            output = root / 'dataset'
            build([run], fixture, output, 'item')
            train = json.loads((output / 'train.json').read_text())
            valid = json.loads((output / 'validation.json').read_text())
            self.assertEqual([(r['source_tick'], r['label']) for r in train], [(700, cases[0]['expected_item'])])
            self.assertEqual([(r['source_tick'], r['label']) for r in valid], [(0, cases[1]['expected_item'])])
            self.assertNotEqual(train[0]['label'], '30')
            self.assertEqual(train[0]['kind'], 'item')
            self.assertEqual(set(train[0]['question']['criteria']), set(cases[0]['packet']['questions']['item']['criteria']))
            self.assertNotIn('Current command:', train[0]['state'])
            self.assertIn('Current command:', train[0]['raw_state'])


if __name__ == '__main__':
    unittest.main()
