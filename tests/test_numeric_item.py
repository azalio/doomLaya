import importlib.util
from types import SimpleNamespace
import unittest
from doomlib.numeric_item import FORMAT,CATEGORY_FORMAT,observations,make_model,predict

STATE='HP 100; armor 0.\nInventory: melee 0 ammo; pistol 38 ammo; shotgun 1 ammo.'
QUESTION=dict(type='choice',instructions='Choose item.',criteria={'h':'0.6m Health Stimpack reachable','s':'5.2m Weapon Shotgun reachable owned'})


def spec():
    names=['Shotgun','Stimpack'];values=observations(STATE,QUESTION,names)
    return dict(format=FORMAT,question='item',input_projection=CATEGORY_FORMAT,item_names=names,features=len(values[0]),thresholds={},hidden_size=4,probability_floor=.0001)


class NumericItemObservationTests(unittest.TestCase):
    def test_observations_do_not_remove_full_health_pickup(self):
        values=observations(STATE,QUESTION,['Shotgun','Stimpack'])
        self.assertEqual(len(values),2)
        self.assertEqual(values[0][0],1)
        self.assertEqual(values[0][47],.6/32)
        self.assertEqual(values[1][47],5.2/32)
        self.assertEqual(values[1][-2:], [1, .01])


@unittest.skipUnless(importlib.util.find_spec('torch'),'Requires model Python with Torch')
class NumericItemNetworkTests(unittest.TestCase):
    def test_identity_and_learned_ranking_preserve_every_option(self):
        import torch
        config=spec();model=make_model(config)
        x=torch.tensor([observations(STATE,QUESTION,config['item_names'])]);b=torch.tensor([[-.1,-2.]])
        self.assertTrue(torch.equal(model(x,b),b))
        with torch.no_grad():
            for parameter in model.network.parameters():parameter.zero_()
            model.network[0].weight[0,55]=1  # Observed Shotgun name, no policy rule.
            model.network[2].weight[0,0]=1
            model.network[4].weight[0,0]=10
        original=dict(model='laya-rl-agent',usage={'input_tokens':12},answers={'item':dict(type='choice',choice='h',probabilities={'h':.9,'s':.1})})
        agent=SimpleNamespace(device=torch.device('cpu'),numeric_residual=model,numeric_residual_spec=config,_semantic_predict=lambda *_:original)
        result=predict(agent,STATE,{'item':QUESTION})['answers']['item']
        self.assertEqual(result['choice'],'s')
        self.assertEqual(set(result['probabilities']),{'h','s'})
        self.assertAlmostEqual(sum(result['probabilities'].values()),1)
        self.assertEqual(result['numeric_residual']['semantic_answer']['choice'],'h')
        reversed_question=dict(QUESTION,criteria=dict(reversed(list(QUESTION['criteria'].items()))))
        reversed_result=predict(agent,STATE,{'item':reversed_question})['answers']['item']
        self.assertEqual(reversed_result['choice'],'s')

    def test_changed_feature_width_is_rejected(self):
        config=spec();config['features']+=1
        with self.assertRaises(ValueError):make_model(config)

if __name__=='__main__':unittest.main()
