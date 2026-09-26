"""Measured clearance informs the model without changing its available actions."""
import copy
import unittest
from decision_questions import MOVEMENTS
from movement_questions import with_movement_clearance


class MovementFactsTest(unittest.TestCase):
    def test_only_movement_question_changes_and_continue_uses_previous_direction(self):
        packet={'state':'unchanged state','commands':{'attack':{}},'current_movement':'backward','questions':{'command':{'criteria':{'attack':'Fight'}},'movement':{'instructions':'Choose.','criteria':dict(MOVEMENTS,continue_='unused')}}}
        packet['questions']['movement']['criteria'].pop('continue_')
        packet['questions']['movement']['criteria']['continue']='Continue backward.'
        before=copy.deepcopy(packet)
        actual=with_movement_clearance(packet,{'left':.25,'right':7.75,'back':.25})
        self.assertEqual(actual['state'],before['state'])
        self.assertEqual(actual['commands'],before['commands'])
        self.assertEqual(actual['questions']['command'],before['questions']['command'])
        self.assertEqual(list(actual['questions']['movement']['criteria']),list(before['questions']['movement']['criteria']))
        self.assertIn('0.25m',actual['questions']['movement']['criteria']['continue'])
        self.assertIn('7.75m',actual['questions']['movement']['criteria']['strafe_right'])
        self.assertNotIn('choice',actual)

    def test_training_pairs_change_only_backward_space_and_select_an_open_route(self):
        import random
        from training.build_movement_clearance_curriculum import pairs
        for seed in range(16):
            rows=pairs(random.Random(seed),seed)
            self.assertEqual(rows[0]['state'],rows[1]['state'])
            self.assertEqual(list(rows[0]['question']['criteria']),list(rows[1]['question']['criteria']))
            self.assertNotEqual(rows[0]['label'],rows[1]['label'])
            for row in rows:
                choice=row['label']
                if choice=='continue':
                    import re
                    choice=re.search(r'Movement: ([^.]+)',row['state'])[1]
                side={'backward':'back','strafe_left':'left','strafe_right':'right'}[choice]
                self.assertGreaterEqual(row['clearance'][side],3)

    def test_explicit_movement_removes_only_duplicate_alias(self):
        from movement_questions import without_movement_continuation, explicit_example
        packet={'state':'Movement: backward.', 'current_movement':'backward', 'questions':{'movement':{'instructions':'Choose.', 'criteria':dict(MOVEMENTS, **{'continue':'Continue backward.'})}}}
        before=copy.deepcopy(packet)
        result=without_movement_continuation(packet)
        self.assertEqual(result['state'],before['state'])
        self.assertEqual(result['questions']['movement']['criteria'],MOVEMENTS)
        row={'kind':'movement','state':before['state'],'question':before['questions']['movement'],'label':'continue'}
        converted=explicit_example(row)
        self.assertEqual(converted['label'],'backward')
        self.assertNotIn('continue',converted['question']['criteria'])
        self.assertEqual(row['label'],'continue')
        self.assertEqual(converted['state'],row['state'])

    def test_rejects_missing_or_invalid_measurement(self):
        for clearance in ({'left':1,'right':1},{'left':1,'right':1,'back':float('nan')},{'left':1,'right':1,'back':-1}):
            packet={'questions':{'movement':{'instructions':'Choose.','criteria':MOVEMENTS}}}
            with self.assertRaises(ValueError):with_movement_clearance(packet,clearance)


if __name__=='__main__':unittest.main()
