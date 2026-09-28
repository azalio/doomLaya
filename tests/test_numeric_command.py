import copy
import importlib.util
import math
from types import SimpleNamespace
import unittest
from doomlib.command_facts import stable_command_facts_input
from doomlib.numeric_command import ACTIONS, FORMAT, FUSION_FORMAT, FEATURE_FORMAT, STABLE_FORMAT, feature_names, features, make_residual_model, predict_with_numeric_residual, semantic_logits
from tests import test_command_facts


def sample():
    question=dict(type='choice',instructions='Choose.',criteria={'attack':'Fight','pickup':'Collect','wait':'Wait'})
    state,question=stable_command_facts_input(test_command_facts.CommandFactsTests().state(),question)
    return dict(state=state,question=question)


def spec():
    names=['BlueCard','Medikit','Shotgun']
    return dict(format=FORMAT,feature_format=FEATURE_FORMAT,input_projection=STABLE_FORMAT,
        actions=list(ACTIONS),item_names=names,feature_names=feature_names(names),thresholds={'0':[0.35,0.75]},hidden_size=8,probability_floor=0.0001)


class NumericFeatureTests(unittest.TestCase):
    def test_numbers_retain_inventory_and_selected_lift(self):
        config=spec();observed=dict(zip(config['feature_names'],features(sample(),config['item_names']),strict=True))
        self.assertEqual(observed['health'],0.13)
        self.assertEqual(observed['shotgun_ammo'],0.05)
        self.assertEqual(observed['selected_lift_present'],1)
        self.assertEqual(observed['item_Shotgun_distance'],3.5/32)
        self.assertEqual(observed['available_attack'],1)
        self.assertEqual(observed['available_exit'],0)

    def test_zero_rounded_probabilities_remain_finite(self):
        values=semantic_logits({'probabilities':{'attack':1,'pickup':0}})
        self.assertTrue(all(math.isfinite(v) for v in values))
        self.assertEqual(values[0],0)


@unittest.skipUnless(importlib.util.find_spec('torch'), 'Requires model Python with Torch')
class NumericNetworkTests(unittest.TestCase):
    def test_zero_residual_preserves_semantic_scores(self):
        import torch
        config=spec();model=make_residual_model(config)
        observed=torch.tensor([features(sample(),config['item_names'])]);semantic=torch.arange(8,dtype=torch.float32)[None,:]
        self.assertTrue(torch.equal(model(observed,semantic),semantic))

    def test_learned_scores_choose_only_offered_actions(self):
        import torch
        config=spec();model=make_residual_model(config)
        with torch.no_grad():
            model.network[-1].bias[ACTIONS.index('pickup')]=10
            model.network[-1].bias[ACTIONS.index('exit')]=100
        original=dict(model='laya-rl-agent',usage={'input_tokens':12},answers={'command':dict(type='choice',choice='attack',probabilities={'attack':0.8,'pickup':0.1,'wait':0.1})})
        calls=[]
        def semantic(state,questions):calls.append((state,questions));return copy.deepcopy(original)
        agent=SimpleNamespace(numeric_residual=model,numeric_residual_spec=config,device=torch.device('cpu'),_semantic_predict=semantic)
        row=sample();result=predict_with_numeric_residual(agent,row['state'],{'command':row['question']})
        answer=result['answers']['command']
        self.assertEqual(answer['choice'],'pickup')
        self.assertEqual(set(answer['probabilities']),set(row['question']['criteria']))
        self.assertAlmostEqual(sum(answer['probabilities'].values()),1)
        self.assertEqual(answer['numeric_residual']['semantic_answer'],original['answers']['command'])
        self.assertEqual(len(calls),1)

    def test_fusion_weight_is_learned_and_starts_as_semantic_identity(self):
        import torch
        config=spec();config['format']=FUSION_FORMAT
        model=make_residual_model(config)
        observed=torch.tensor([features(sample(),config['item_names'])])
        semantic=torch.arange(8,dtype=torch.float32)[None,:]
        self.assertTrue(torch.equal(model(observed,semantic),semantic))
        model(observed,semantic).sum().backward()
        self.assertIsNotNone(model.semantic_scale.grad)
        self.assertGreater(float(model.semantic_scale.grad),0)

    def test_rejects_wrong_schema(self):
        config=spec();config['feature_names'][0]='teacher_command'
        with self.assertRaises(ValueError):make_residual_model(config)

if __name__=='__main__':unittest.main()
