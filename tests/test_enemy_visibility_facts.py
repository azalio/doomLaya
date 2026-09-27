import copy
import unittest
from doomlib.decision_questions import with_enemy_visibility_facts


class EnemyVisibilityFactsTest(unittest.TestCase):
    def test_facts_preserve_hidden_targets_and_other_questions(self):
        packet = dict(state='Current command: attack #1',
            targets=dict(enemy={'1':dict(visible=False), '2':dict(visible=True)}),
            questions=dict(enemy=dict(criteria={'1':'Zombieman 3m.', '2':'DoomImp 5m.'}),
                           weapon=dict(criteria={'shotgun':'Loaded gun'})))
        original = copy.deepcopy(packet)
        actual = with_enemy_visibility_facts(packet)
        self.assertEqual(packet, original)
        self.assertEqual(list(actual['questions']['enemy']['criteria']), ['1', '2'])
        self.assertEqual(actual['targets'], packet['targets'])
        self.assertEqual(actual['state'], packet['state'])
        self.assertEqual(actual['questions']['weapon'], packet['questions']['weapon'])
        self.assertEqual(actual['questions']['enemy']['criteria'], {
            '1':'Not visible now; last seen. Zombieman 3m.',
            '2':'Visible now. DoomImp 5m.'})

    def test_no_enemies_does_not_add_a_question(self):
        packet = dict(state='No enemies', questions={'command':{}}, targets={})
        self.assertEqual(with_enemy_visibility_facts(packet), packet)


if __name__ == '__main__':
    unittest.main()
