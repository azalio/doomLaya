import copy
import importlib.util
import unittest
from types import SimpleNamespace

from doomlib.enemy_ranking import STOP, sequence_probabilities
from doomlib.numeric_enemy import FORMAT, PROJECTION, FEATURES, observations, make_model, predict


def question():
    return dict(type='choice',criteria={
        '7':'DoomImp; distance 4.0m; bearing -10 degrees; visible; latest accepted target: yes.',
        '8':'ShotgunGuy; distance 12.0m; bearing 30 degrees; last seen; latest accepted target: no.',
        STOP:'End the firing sequence before any remaining targets.'})


class EnemyFactsTests(unittest.TestCase):
    def test_ids_and_presentation_do_not_change_candidate_features(self):
        q=question();first=observations('',q)
        renamed=dict(q,criteria={'other':q['criteria']['8'],STOP:q['criteria'][STOP],'new':q['criteria']['7']})
        self.assertEqual(observations('',renamed),[first[1],first[2],first[0]])

    def test_visible_and_previous_are_independent_observations(self):
        rows=observations('',question())
        self.assertEqual(rows[0][FEATURES.index('visible')],1)
        self.assertEqual(rows[1][FEATURES.index('visible')],0)
        self.assertEqual(rows[0][FEATURES.index('previous')],1)
        self.assertEqual(rows[1][FEATURES.index('previous')],0)
        self.assertEqual(rows[2][FEATURES.index('stop')],1)

    def test_missing_end_or_ambiguous_previous_target_is_rejected(self):
        q=question();q['criteria'].pop(STOP)
        with self.assertRaises(ValueError):observations('',q)
        q=question();q['criteria']['8']=q['criteria']['8'].replace('target: no.','target: yes.')
        with self.assertRaises(ValueError):observations('',q)


@unittest.skipUnless(importlib.util.find_spec('torch'),'requires torch')
class EnemyNetworkTests(unittest.TestCase):
    def test_zero_residual_preserves_complete_ranking_distribution(self):
        import torch
        spec=dict(format=FORMAT,input_projection=PROJECTION,features=list(FEATURES),thresholds={},hidden_size=8,probability_floor=1e-30)
        probability={'7':.6,'8':.4-1e-12,STOP:1e-12}
        original=dict(answers={'enemy':dict(type='choice',choice='7',probabilities=probability)},usage={})
        agent=SimpleNamespace(device=torch.device('cpu'),numeric_residual_spec=spec,numeric_residual=make_model(spec),
                              _semantic_predict=lambda state,questions:copy.deepcopy(original))
        actual=predict(agent,'',{'enemy':question()})['answers']['enemy']['probabilities']
        orders={'a':['7'],'b':['8'],'ab':['7','8'],'ba':['8','7']}
        before=sequence_probabilities(probability,orders);after=sequence_probabilities(actual,orders)
        self.assertEqual(set(actual),set(probability))
        for key in before:self.assertAlmostEqual(before[key],after[key],places=6)

    def test_listwise_loss_masks_padding_and_first_step_stop(self):
        import torch
        from training.finetune_numeric_enemy import ranking_loss
        scores=torch.tensor([[2.,1.,0.,1000.]],requires_grad=True)
        loss=ranking_loss(scores,torch.tensor([[True,True,True,False]]),torch.tensor([[0,1,2,-1]]),torch.tensor([2]))
        self.assertAlmostEqual(float(loss.detach()),4*float(torch.log1p(torch.exp(torch.tensor(-1.)))),places=6)
        loss.backward()
        self.assertEqual(float(scores.grad[0,3]),0)


if __name__=='__main__':unittest.main()
