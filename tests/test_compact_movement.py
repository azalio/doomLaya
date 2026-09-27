"""Compact observations preserve explicit model control and measured facts."""
import copy, unittest
from doomlib.compact_movement import compact_movement_input, movement_facts
from doomlib.decision_questions import MOVEMENTS
from doomlib.movement_questions import describe_movement
from doomlib.question_heads import QuestionHeads
from tests.test_question_heads import Stub


class CompactMovementTests(unittest.TestCase):
    def sample(self):
        state='Current command: pickup #40.\nEnemies: DoomImp#1 3.0m (last seen); Zombieman#2 8.0m (visible).\nMovement: strafe_right.'
        question=describe_movement(dict(type='choice',instructions='Original question.',criteria=MOVEMENTS),dict(left=.5,right=4,back=2))
        return state, question

    def test_facts_match_visible_priority_and_exact_clearance_boundaries(self):
        state, question=self.sample(); facts=movement_facts(state,question)
        self.assertEqual(facts,dict(nearest=8,known_enemies=2,visible_enemies=1,current='strafe_right',clearance=dict(left=.5,right=4,back=2)))
        text, _=compact_movement_input(state,question)
        self.assertIn('Body clearance left: 0.50 meters. At least two meters: no. At least four meters: no.',text)
        self.assertIn('Body clearance back: 2.00 meters. At least two meters: yes. At least four meters: no.',text)
        self.assertIn('Body clearance right: 4.00 meters. At least two meters: yes. At least four meters: yes.',text)

    def test_preserves_every_choice_and_input(self):
        state, question=self.sample(); before=copy.deepcopy(question)
        text, result=compact_movement_input(state,question)
        self.assertEqual(question,before);self.assertEqual(result['criteria'],question['criteria'])
        self.assertNotIn('pickup',text)
        self.assertNotIn('5 meters',result['instructions'])

    def test_missing_enemies_clearance_or_explicit_direction_fails(self):
        state, question=self.sample()
        with self.assertRaises(ValueError):compact_movement_input('Movement: stationary.',question)
        q=copy.deepcopy(question);q['criteria']['backward']='Back'
        with self.assertRaises(ValueError):compact_movement_input(state,q)
        q=copy.deepcopy(question);q['criteria']['continue']='Continue'
        with self.assertRaises(ValueError):compact_movement_input(state,q)

    def test_shared_head_routes_movement_separately_and_preserves_answers(self):
        state, question=self.sample();shared=Stub('model_choice')
        heads=QuestionHeads(shared,dict(movement=shared,command=shared),command_without_goal=True,movement_compact_facts=True)
        result=heads.predict(state,dict(movement=question,command={'criteria':{'attack':'Attack'}}))
        self.assertEqual(len(shared.calls),2)
        self.assertEqual(shared.calls[0],(compact_movement_input(state,question)[0],{'movement':compact_movement_input(state,question)[1]}))
        self.assertEqual(result['answers']['movement']['choice'],'model_choice')
        self.assertEqual(result['usage']['input_tokens'],22)


if __name__=='__main__':unittest.main()
