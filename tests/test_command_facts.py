import copy
import unittest
from doomlib.command_facts import command_facts_input, stable_command_facts_input, STABLE_FORMAT, binned_command_facts_input, observed_band, BINNED_FORMAT


class CommandFactsTests(unittest.TestCase):
    def state(self):
        return ('Current command: use_switch #805; status executing.\n'
                'Reachable items: Shotgun#1, Shotgun#2, Medikit#3, BlueCard#4.\n'
                'Available mechanisms: lift #805 phase board 2.0m Upper route keys: blue (missing).; floor switch #9 20.0m (lowers floor) Exit platform.\n'
                'HP 13; armor 0.\nInventory: melee 0 ammo; pistol 30 ammo; shotgun 5 ammo; BFG 20 ammo.\nCollected keys: red.\n'
                'Enemies: DoomImp#10 25.0m (visible); ShotgunGuy#11 4.7m (last seen).\n'
                'Items: Shotgun#1 [Weapon] 3.5m; Shotgun#2 [Weapon] 12.0m; Medikit#3 [Health] 15.0m; BlueCard#4 [Key] 7.0m; SuperShotgun#5 [Weapon] 1.0m.')

    def test_observed_minima_ownership_and_visibility(self):
        state, _ = command_facts_input(self.state(), {})
        self.assertIn('Loaded ranged weapons: pistol, shotgun.', state)
        self.assertIn('Shotgun 3.5m, owned yes, ammo 5', state)
        self.assertNotIn('Shotgun 12.0m', state)
        self.assertNotIn('SuperShotgun', state)
        self.assertIn('visible count 1, nearest 25.0m', state)
        self.assertIn('last seen count 1, nearest 4.7m', state)
        self.assertIn('Reachable Health items: Medikit 15.0m.', state)
        self.assertIn('Reachable Key items: BlueCard 7.0m.', state)

    def test_current_goal_lift_and_exit_are_facts(self):
        state, _ = command_facts_input(self.state(), {})
        self.assertIn('Current command: use_switch #805; status executing.', state)
        self.assertIn('Available mechanisms: 2; exit platforms: 1.', state)
        self.assertIn('Boarding or riding lifts: #805 phase board 2.0m.', state)

    def test_question_and_actions_are_unchanged(self):
        question = {'type': 'choice', 'instructions': 'Choose.', 'criteria': {'attack': 'Fight', 'pickup': 'Collect', 'wait': 'Wait'}}
        before = copy.deepcopy(question)
        _, result = command_facts_input(self.state(), question)
        self.assertEqual(result, before)
        self.assertEqual(question, before)
        self.assertIsNot(result, question)

    def test_model_keeps_authority_and_other_heads_keep_original_state(self):
        from doomlib.question_heads import QuestionHeads
        from tests.test_question_heads import Stub
        model = Stub('wait')
        heads = QuestionHeads(model, {'command': model}, command_compact_facts=True)
        question = {'type': 'choice', 'criteria': {'attack': 'Fight', 'pickup': 'Collect', 'wait': 'Wait'}}
        result = heads.predict(self.state(), {'command': question, 'weapon': {}})
        self.assertEqual(result['answers']['command']['choice'], 'wait')
        self.assertEqual(model.calls[1][0], self.state())
        self.assertEqual(model.calls[0][1]['command'], question)

    def test_nonlift_goal_cannot_change_stable_input(self):
        world = self.state().split('\n', 1)[1]
        variants = ['pickup #3 Medikit 15.0m', 'use_switch #839 Door switch 27.7m', 'attack #10', 'none']
        question = {'criteria': {'attack': 'Fight', 'pickup': 'Collect', 'use_switch': 'Activate', 'wait': 'Wait'}}
        projections = [stable_command_facts_input('Current command: ' + goal + '; status executing.\n' + world, question) for goal in variants]
        self.assertTrue(all(result == projections[0] for result in projections))
        self.assertNotIn('Current command:', projections[0][0])
        self.assertEqual(projections[0][1], question)

    def test_selected_lift_execution_context_is_retained(self):
        selected, _ = stable_command_facts_input(self.state(), {})
        other, _ = stable_command_facts_input(self.state().replace('use_switch #805;', 'use_switch #999;'), {})
        self.assertIn('Selected lift in progress: #805 phase board 2.0m.', selected)
        self.assertIn('Selected lift in progress: none.', other)
        self.assertIn('Boarding or riding lifts: #805 phase board 2.0m.', other)

    def test_checkpoint_format_selects_stable_projection(self):
        from doomlib.question_heads import QuestionHeads
        from tests.test_question_heads import Stub
        model = Stub('wait')
        model.cfg = {'doom_adaptation': {'input_projection': STABLE_FORMAT}}
        heads = QuestionHeads(model, {'command': model}, command_compact_facts=True)
        question = {'type': 'choice', 'criteria': {'pickup': 'Collect', 'wait': 'Wait'}}
        result = heads.predict(self.state(), {'command': question})
        self.assertEqual(result['answers']['command']['choice'], 'wait')
        self.assertEqual(model.calls[0][0], stable_command_facts_input(self.state(), question)[0])

    def test_measurement_bands_keep_threshold_boundaries(self):
        self.assertEqual(observed_band(5.9, (3, 4, 5, 6, 8, 10, 20)), '[5,6)')
        self.assertEqual(observed_band(6, (3, 4, 5, 6, 8, 10, 20)), '[6,8)')
        self.assertEqual(observed_band(20, (3, 4, 5, 6, 8, 10, 20)), '[20,infinity)')
        selected, _ = binned_command_facts_input(self.state(), {})
        self.assertIn('HP band [0,35); armor band [0,60).', selected)
        self.assertIn('shotgun ammo band [4,15)', selected)
        self.assertIn('Medikit distance band [10,20) meters', selected)
        self.assertIn('nearest distance band [20,infinity) meters', selected)
        self.assertIn('Selected lift in progress: #805 phase board distance band [0,3) meters.', selected)

    def test_values_inside_same_observed_band_have_identical_input(self):
        first, _ = binned_command_facts_input(self.state(), {})
        second, _ = binned_command_facts_input(self.state().replace('HP 13;', 'HP 20;').replace('15.0m', '18.0m'), {})
        self.assertEqual(first, second)

    def test_binned_checkpoint_keeps_model_authority(self):
        from doomlib.question_heads import QuestionHeads
        from tests.test_question_heads import Stub
        model = Stub('wait')
        model.cfg = {'doom_adaptation': {'input_projection': BINNED_FORMAT}}
        heads = QuestionHeads(model, {'command': model}, command_compact_facts=True)
        question = {'type': 'choice', 'criteria': {'attack': 'Fight', 'pickup': 'Collect', 'wait': 'Wait'}}
        result = heads.predict(self.state(), {'command': question, 'weapon': {}})
        self.assertEqual(result['answers']['command']['choice'], 'wait')
        self.assertEqual(model.calls[0], (binned_command_facts_input(self.state(), question)[0], {'command': question}))
        self.assertEqual(model.calls[1][0], self.state())

    def test_missing_inventory_is_not_guessed(self):
        with self.assertRaises(ValueError):
            command_facts_input(self.state().replace('Inventory:', 'Unknown:'), {})

    def test_empty_observations_do_not_imply_an_action(self):
        state = 'HP 100; armor 0.\nInventory: pistol 50 ammo.\nCollected keys: none.\nReachable items: none.'
        result, question = command_facts_input(state, {'criteria': {'pickup': 'Collect', 'exit': 'Exit'}})
        self.assertIn('Available mechanisms: 0; exit platforms: 0.', result)
        self.assertIn('Reachable Health items: none.', result)
        self.assertEqual(list(question['criteria']), ['pickup', 'exit'])


if __name__ == '__main__':
    unittest.main()
