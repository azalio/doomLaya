import copy
import unittest
from model_decoding import ChoiceDecoder


class ModelDecodingTest(unittest.TestCase):
    def result(self):
        return {'answers':{'command':{'type':'choice','choice':'a','probabilities':{'a':.6,'b':.4,'forbidden':0.}}}}

    def test_default_preserves_model_answer(self):
        result=self.result();self.assertEqual(ChoiceDecoder().apply(copy.deepcopy(result)),result)

    def test_sampling_is_seeded_and_uses_only_model_support(self):
        a,b=ChoiceDecoder(.35,48),ChoiceDecoder(.35,48)
        first=[a.apply(self.result())['answers']['command'] for _ in range(100)]
        second=[b.apply(self.result())['answers']['command'] for _ in range(100)]
        self.assertEqual(first,second)
        self.assertEqual({r['choice'] for r in first},{'a','b'})
        for r in first:
            self.assertEqual(r['probabilities'],self.result()['answers']['command']['probabilities'])
            self.assertAlmostEqual(sum(r['decoding']['probabilities'].values()),1.)
        self.assertEqual(first[-1]['decoding']['draw'],100)

    def test_sampling_can_leave_motor_answers_at_argmax(self):
        original=self.result()
        for name in ("movement","weapon","enemy"):
            original["answers"][name]=copy.deepcopy(original["answers"]["command"])
        decoder=ChoiceDecoder(.7,49,["command","item","switch"])
        choices=set()
        for _ in range(100):
            result=decoder.apply(copy.deepcopy(original))
            choices.add(result["answers"]["command"]["choice"])
            for name in ("movement","weapon","enemy"):
                self.assertEqual(result["answers"][name],original["answers"][name])
        self.assertEqual(choices,{"a","b"})
        self.assertEqual(decoder.draws,100)
        self.assertEqual(decoder.metadata()["questions"],["command","item","switch"])

    def test_invalid_temperature_is_rejected(self):
        for temperature in (-1,float('nan'),float('inf')):
            with self.assertRaises(ValueError):ChoiceDecoder(temperature)


if __name__=='__main__':unittest.main()
