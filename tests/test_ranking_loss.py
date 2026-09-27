import importlib.util,itertools,math,unittest
from doomlib.enemy_ranking import STOP,sequence_probabilities


@unittest.skipUnless(importlib.util.find_spec('torch'),'Requires the Laya training environment')
class RankingLossTests(unittest.TestCase):
    def test_training_loss_matches_runtime_sequence_probability(self):
        import torch
        from training.ranking import ranking_loss
        keys=['1','2','3',STOP];order=['2','1',STOP]
        row=dict(question=dict(criteria={key:key for key in keys}),label='2',target_ranking=order)
        z=torch.tensor([[.1,.5,-.2,-.3]],dtype=torch.float64,requires_grad=True)
        orders={str(i):list(order) for i,order in enumerate(order for n in (1,2,3) for order in itertools.permutations(keys[:-1],n))}
        scores=dict(zip(keys,z.softmax(-1).detach()[0].tolist()));p=sequence_probabilities(scores,orders)
        expected=next(v for key,v in p.items() if orders[key]==['2','1'])
        loss=ranking_loss(z,[row]);self.assertAlmostEqual(float(loss.detach()),-math.log(expected),places=10)
        loss.backward();self.assertTrue(torch.isfinite(z.grad).all());self.assertGreater(float(z.grad.abs().sum()),0)

    def test_wrong_order_has_larger_loss_and_single_target_has_zero_loss(self):
        import torch
        from training.ranking import ranking_loss
        row=dict(question=dict(criteria={'1':'one','2':'two',STOP:'stop'}),label='1',target_ranking=['1','2',STOP])
        self.assertLess(float(ranking_loss(torch.tensor([[3.,1.,-3.]]),[row])),float(ranking_loss(torch.tensor([[1.,3.,-3.]]),[row])))
        row=dict(question=dict(criteria={'1':'one',STOP:'stop'}),label='1',target_ranking=['1',STOP])
        self.assertAlmostEqual(float(ranking_loss(torch.tensor([[1.,3.]]),[row])),0)

    def test_precise_inference_preserves_small_target_probabilities(self):
        import torch
        from types import SimpleNamespace
        from doomlib.ranked_inference import predict_precise
        class Tokenizer:
            cls_token_id=1;sep_token_id=2;mask_token_id=3;pad_token_id=0;mask_token='[MASK]'
            def __call__(self,text,add_special_tokens=False):return {'input_ids':[4]*len(text.split())}
        class Model:
            def __call__(self,*args):return torch.tensor([[0.,-12.,-13.,-15.]]),torch.zeros(1,2)
        agent=SimpleNamespace(tok=Tokenizer(),cfg={'max_len':640,'head_max_len':384},model=Model(),device=torch.device('cpu'),dtype=torch.float32,temperature=[1,1,1],temperature_by_options={},_to_internal=lambda q:dict(t=q['type'],ins=q['instructions'],crit=q['criteria']))
        question=dict(type='choice',instructions='Rank targets',criteria={'1':'First','2':'Second','3':'Third',STOP:'Stop'})
        result=predict_precise(agent,'HP 40',{'enemy':question});p=result['answers']['enemy']['probabilities']
        self.assertGreater(p['2'],p['3']);self.assertGreater(p['3'],p[STOP]);self.assertGreater(p[STOP],0)
        self.assertEqual(round(p['2'],4),0);self.assertEqual(result['answers']['enemy']['choice'],'1')
        self.assertGreater(result['usage']['input_tokens'],0)
