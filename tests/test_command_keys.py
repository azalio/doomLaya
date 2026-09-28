import copy
import unittest
from doomlib.command_keys import command_key_input
from doomlib.question_heads import QuestionHeads
from tests.test_question_heads import Stub


class CommandKeyFactsTests(unittest.TestCase):
    def state(self):
        return 'Current command: use_switch #8.\nReachable items: Medikit#1, BlueCard#27.\nHP 38; armor 55.\nCollected keys: red.\nItems: Medikit#1 [Health] 13.3m; BlueCard#27 [Key] 12.6m; YellowCard#key_21 [Key] 40.4m.'

    def test_exposes_only_observed_reachable_keys_and_keeps_choices(self):
        q=dict(type='choice',instructions='Choose',criteria={'pickup':'Pick','use_switch':'Use','wait':'Wait'})
        original=copy.deepcopy(q);state,result=command_key_input(self.state(),q)
        self.assertEqual(state.splitlines()[0],'Reachable keys: BlueCard#27 12.6m.')
        self.assertEqual(result,original);self.assertEqual(q,original)
        self.assertEqual(state.splitlines()[1:],self.state().splitlines()[1:])

    def test_projection_does_not_choose_action_or_change_other_heads(self):
        model=Stub('wait');heads=QuestionHeads(model,{'command':model},command_key_facts=True)
        q=dict(type='choice',criteria={'pickup':'Pick','use_switch':'Use','wait':'Wait'})
        result=heads.predict(self.state(),{'command':q,'weapon':{}})
        self.assertEqual(result['answers']['command']['choice'],'wait')
        self.assertEqual(model.calls[1][0],self.state())
        self.assertEqual(model.calls[0][1]['command']['criteria'],q['criteria'])

    def test_requires_explicit_reachability(self):
        with self.assertRaises(ValueError):command_key_input('Items: BlueCard#1 [Key] 2.0m.',{})

    def test_none_is_an_observation_not_a_removed_action(self):
        state,q=command_key_input('Reachable items: Medikit#1.\nItems: Medikit#1 [Health] 2.0m.',{'criteria':{'pickup':'Pick'}})
        self.assertTrue(state.startswith('Reachable keys: none.'))
        self.assertIn('pickup',q['criteria'])

    def test_color_contrast_changes_inventory_route_facts_and_objects_together(self):
        from training.build_command_key_facts import recolor
        state='Reachable keys: BlueCard#27 12.6m.\nCollected keys: red.\nAvailable mechanisms: Upper route keys: red (collected); blue (missing).'
        row=dict(state=state,raw_state=state,label='pickup',question={'criteria':{'pickup':'Pick','use_switch':'Use'}},source_run='original',source_tick=1)
        mapping={'blue':'yellow','red':'blue','yellow':'red'}
        out=recolor(row,mapping)
        self.assertIn('YellowCard#27',out['state'])
        self.assertIn('Collected keys: blue.',out['state'])
        self.assertIn('blue (collected); yellow (missing)',out['state'])
        self.assertEqual(out['question'],row['question'])
        self.assertEqual(row['state'],state)

    def test_training_and_server_projection_match(self):
        from training.build_command_key_facts import project_keys
        row=dict(kind='command',label='pickup',state=self.state(),question=dict(type='choice',instructions='Finish the level alive.',criteria={'pickup':'Pick','wait':'Wait'}))
        out=project_keys(row)
        expected=command_key_input(row['state'],row['question'])
        self.assertEqual((out['state'],out['question']),expected)


if __name__=='__main__':unittest.main()
