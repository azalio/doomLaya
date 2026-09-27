import copy,unittest
from doomlib.enemy_ranking import STOP,ranking_input,sequence_probabilities,decode_ranking
from doomlib.enemy_sequences import with_enemy_sequences
from training.ranking import validate_ranking


class EnemyRankingTests(unittest.TestCase):
    def sample(self,n=3):
        state='HP 40; armor 0.\nInventory: shotgun 20 ammo.'
        packet=with_enemy_sequences(dict(state=state,questions={'enemy':{}},enemy_commitment=dict(target_id=2),targets={'enemy':{str(i):dict(id=i,name='DoomImp',distance=i*3,bearing=i*10,visible=i!=3) for i in range(1,n+1)}}))
        return state,packet['questions']['enemy']

    def test_every_original_choice_is_preserved_with_local_target_facts(self):
        state,q=self.sample();before=copy.deepcopy(q);s,r,orders=ranking_input(state,q)
        self.assertEqual(q,before);self.assertEqual(s,state);self.assertEqual(len(orders),15)
        self.assertIn('latest accepted target: yes',r['criteria']['2'])
        self.assertIn('last seen',r['criteria']['3']);self.assertEqual(set(r['criteria']),{'1','2','3',STOP})

    def test_probabilities_cover_all_nonempty_ordered_subsets(self):
        for n in (1,2,3):
            s,q=self.sample(n);_,rank,orders=ranking_input(s,q)
            p=sequence_probabilities({key:1 for key in rank['criteria']},orders)
            self.assertAlmostEqual(sum(p.values()),1);self.assertEqual(set(p),set(q['criteria']));self.assertTrue(all(value>0 for value in p.values()))

    def test_model_scores_can_select_single_target_or_full_order(self):
        s,q=self.sample();_,_,orders=ranking_input(s,q)
        answer=decode_ranking(dict(probabilities={'1':.7,'2':.2,'3':.09,STOP:.01}),orders)
        self.assertEqual(orders[answer['choice']],['1','2','3'])
        answer=decode_ranking(dict(probabilities={'1':.1,'2':.2,'3':.05,STOP:.65}),orders)
        self.assertEqual(orders[answer['choice']],['2'])
        answer=decode_ranking(dict(probabilities={'1':.01,'2':.1,'3':.8,STOP:.09}),orders)
        self.assertEqual(orders[answer['choice']][0],'3')

    def test_zero_rounded_probabilities_and_bad_scores(self):
        s,q=self.sample();_,_,orders=ranking_input(s,q)
        p=sequence_probabilities({'1':1,'2':0,'3':0,STOP:0},orders);self.assertAlmostEqual(sum(p.values()),1)
        with self.assertRaises(ValueError):sequence_probabilities({'1':1},orders)
        with self.assertRaises(ValueError):sequence_probabilities({'1':1,'2':0,'3':0,STOP:float('nan')},orders)

    def test_missing_or_fabricated_sequence_is_rejected(self):
        s,q=self.sample();q['criteria'].pop('0')
        with self.assertRaises(ValueError):ranking_input(s,q)
        s,q=self.sample();q['criteria']['0']='Shoot #999.'
        with self.assertRaises(ValueError):ranking_input(s,q)

    def test_training_order_requires_unique_known_targets_and_final_stop(self):
        s,q=self.sample();_,rank,_=ranking_input(s,q);row=dict(question=rank,label='2',target_ranking=['2','1',STOP]);validate_ranking(row)
        row['target_ranking']=['2','2',STOP]
        with self.assertRaises(ValueError):validate_ranking(row)

    def test_question_router_uses_model_scores_without_distance_ranking(self):
        from doomlib.question_heads import QuestionHeads
        class Model:
            def __init__(self):self.calls=[]
            def predict(self,state,questions):
                self.calls.append((state,questions))
                return dict(model='neural',usage={'input_tokens':5},answers={'enemy':dict(type='choice',choice='3',probabilities={'1':.01,'2':.1,'3':.88,STOP:.01})})
        model=Model();state,q=self.sample();heads=QuestionHeads(model,dict(enemy=model),enemy_rank_facts=True)
        result=heads.predict(state,{'enemy':q});_,_,orders=ranking_input(state,q)
        self.assertEqual(orders[result['answers']['enemy']['choice']],['3','2'])
        self.assertEqual(set(model.calls[0][1]['enemy']['criteria']),{'1','2','3',STOP})
        self.assertEqual(set(result['answers']['enemy']['probabilities']),set(q['criteria']))
        with self.assertRaises(ValueError):QuestionHeads(model,{},enemy_rank_facts=True,enemy_compact_facts=True)
