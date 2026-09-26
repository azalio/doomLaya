"""Question routing preserves model choices without inspecting game state."""
import unittest
from doomlib.question_heads import QuestionHeads


class Stub:
    def __init__(self,label):self.label=label;self.calls=[]
    def predict(self,state,questions):
        self.calls.append((state,questions))
        return dict(model='laya',answers={name:{'choice':self.label} for name in questions},usage={'input_tokens':len(questions)*11,'output_tokens':0})


class QuestionHeadsTest(unittest.TestCase):
    def test_mixed_batch_preserves_answers_order_state_and_token_accounting(self):
        base=Stub('base');items=Stub('trained');heads=QuestionHeads(base,{'item':items})
        state='HP 100; arbitrary current goal';questions={'combat':{},'item':{},'weapon':{}}
        result=heads.predict(state,questions)
        self.assertEqual(list(result['answers']),list(questions))
        self.assertEqual(result['answers'],{'combat':{'choice':'base'},'item':{'choice':'trained'},'weapon':{'choice':'base'}})
        self.assertEqual(base.calls,[(state,{'combat':{},'weapon':{}})])
        self.assertEqual(items.calls,[(state,{'item':{}})])
        self.assertEqual(result['usage']['input_tokens'],33)

    def test_without_item_uses_only_original_model(self):
        base=Stub('base');items=Stub('trained');heads=QuestionHeads(base,{'item':items})
        heads.predict('unrelated state',{'command':{},'switch':{}})
        self.assertEqual(len(base.calls),1);self.assertEqual(items.calls,[])


class HeadSpecsTest(unittest.TestCase):
    def test_multiple_questions_can_share_one_checkpoint(self):
        from doomlib.question_heads import parse_head_specs
        self.assertEqual(parse_head_specs(['command=models/shared','item=models/shared']),
                         {'command':'models/shared','item':'models/shared'})
        self.assertEqual(parse_head_specs([], 'models/legacy'), {'item':'models/legacy'})

    def test_rejects_ambiguous_and_misspelled_head_routes(self):
        from doomlib.question_heads import parse_head_specs
        for specs,legacy in [(['item=models/new'],'models/old'),(['command=x','command=y'],None),(['typo=x'],None),(['item='],None),(['item'],None)]:
            with self.subTest(specs=specs):
                with self.assertRaises(ValueError):parse_head_specs(specs,legacy)


if __name__=='__main__':unittest.main()
