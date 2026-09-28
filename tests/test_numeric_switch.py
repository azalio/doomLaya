import copy
import unittest
from types import SimpleNamespace
from doomlib.numeric_switch import FORMAT, PROJECTION, FEATURES, observations, make_model, predict

try:
    import torch
except ImportError:
    torch = None


class SwitchFeaturesTest(unittest.TestCase):
    def example(self):
        state = 'Collected keys: red.\nCurrent command: use_switch #8 Lift 3.0m; status executing.'
        question = dict(type='choice', instructions='Choose.', criteria={
            '8': 'Call, board and ride lift #8 to the upper floor. Phase: ride. Distance 3.0m. Upper route keys: red (collected).',
            '9': 'Activate floor switch #9 to lower the floor and open a route. Distance 10.0m. Exit platform.'})
        return state, question

    def test_observations_preserve_all_choices_and_capture_physical_context(self):
        state, question = self.example()
        original = copy.deepcopy(question)
        values = observations(state, question)
        self.assertEqual(question, original)
        self.assertEqual(len(values), 2)
        self.assertEqual(len(values[0]), len(FEATURES))
        self.assertEqual(values[0][FEATURES.index('current')], 1)
        self.assertEqual(values[0][FEATURES.index('phase_ride')], 1)
        self.assertEqual(values[0][FEATURES.index('collected_route_red')], 1)
        self.assertEqual(values[1][FEATURES.index('exit_platform')], 1)
        reversed_question = dict(question, criteria=dict(reversed(list(question['criteria'].items()))))
        self.assertEqual(observations(state, reversed_question), list(reversed(values)))

    def test_actor_ids_are_not_numeric_features(self):
        state, question = self.example()
        renamed = dict(question, criteria={str(int(key) + 1000): text.replace('#' + key, '#' + str(int(key) + 1000))
                                          for key, text in question['criteria'].items()})
        self.assertEqual(observations(state, question), observations(state.replace('#8', '#1008'), renamed))

    def test_missing_physical_facts_fail_explicitly(self):
        _, question = self.example()
        with self.assertRaises(ValueError):
            observations('No keys fact.', question)
        with self.assertRaises(ValueError):
            observations('Collected keys: none.', dict(criteria={'1': 'Ready'}))

    @unittest.skipUnless(torch, 'Torch required for learned residual inference')
    def test_learned_scores_can_choose_farther_option_and_keep_original_text(self):
        state, question = self.example()
        spec = dict(format=FORMAT, input_projection=PROJECTION, features=list(FEATURES),
                    thresholds={}, hidden_size=4, probability_floor=.0001)
        model = make_model(spec)
        with torch.no_grad():
            for parameter in model.parameters():
                parameter.zero_()
            model.network[0].weight[0, FEATURES.index('distance')] = 1
            model.network[2].weight[0, 0] = 1
            model.network[4].weight[0, 0] = 1
        seen = []
        def semantic(actual_state, actual_questions):
            seen.append((actual_state, actual_questions))
            return dict(model='test', usage={}, answers={'switch': dict(type='choice', choice='8', probabilities={'8': .9, '9': .1})})
        agent = SimpleNamespace(device='cpu', numeric_residual=model, numeric_residual_spec=spec, _semantic_predict=semantic)
        answer = predict(agent, state, {'switch': question})['answers']['switch']
        self.assertEqual(answer['choice'], '9')
        self.assertEqual(set(answer['probabilities']), {'8', '9'})
        self.assertEqual(seen, [(state, {'switch': question})])
        self.assertEqual(answer['numeric_residual']['semantic_answer']['choice'], '8')


if __name__ == '__main__':
    unittest.main()
