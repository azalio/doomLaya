"""State projection preserves complete enemy facts, choices and model outputs."""
import copy, unittest
from doomlib.compact_enemy import compact_enemy_input
from doomlib.enemy_sequences import with_enemy_sequences
from doomlib.question_heads import QuestionHeads
from tests.test_question_heads import Stub


class CompactEnemyTests(unittest.TestCase):
    def sample(self):
        state='Current command: pickup #40.\nHP 52; armor 0.\nInventory: shotgun 8 ammo; chaingun 50 ammo.\nReachable items: RedCard#40.'
        packet=with_enemy_sequences(dict(state=state,questions={'enemy':{}},targets={'enemy':{
            '1':dict(id=1,name='Zombieman',distance=8,bearing=30,visible=True),
            '2':dict(id=2,name='DoomImp',distance=6,bearing=-10,visible=False)}}))
        return state, packet['questions']['enemy']

    def test_projection_keeps_observed_health_inventory_and_complete_question(self):
        state, question=self.sample();before=copy.deepcopy(question)
        projected, result=compact_enemy_input(state,question)
        self.assertEqual(projected,'HP 52; armor 0.\nInventory: shotgun 8 ammo; chaingun 50 ammo.')
        self.assertEqual(question,before);self.assertEqual(result,before)
        self.assertEqual(len(result['criteria']),4)
        self.assertIn('last seen',result['instructions'])

    def test_route_context_does_not_change_projected_input(self):
        state, question=self.sample()
        self.assertEqual(compact_enemy_input(state,question),compact_enemy_input(state+'\nUnreachable: #84.',question))

    def test_missing_facts_or_legacy_question_fails(self):
        state, question=self.sample()
        with self.assertRaises(ValueError):compact_enemy_input('HP 52;',question)
        with self.assertRaises(ValueError):compact_enemy_input(state,dict(type='choice',instructions='Choose enemy',criteria={'1':'Enemy'}))
        with self.assertRaises(ValueError):compact_enemy_input(state+'\nHP 10;',question)

    def test_shared_head_keeps_other_question_state_and_output_unchanged(self):
        state, question=self.sample();shared=Stub('model_choice')
        heads=QuestionHeads(shared,dict(enemy=shared,weapon=shared),enemy_without_goal=True,enemy_compact_facts=True)
        weapon=dict(type='choice',instructions='Choose weapon',criteria={'shotgun':'Shotgun'})
        result=heads.predict(state,dict(enemy=question,weapon=weapon))
        self.assertEqual(shared.calls,[(compact_enemy_input(state,question)[0],{'enemy':question}),(state,{'weapon':weapon})])
        self.assertEqual(result['answers']['enemy']['choice'],'model_choice')
        self.assertEqual(result['usage']['input_tokens'],22)


if __name__=='__main__':unittest.main()
