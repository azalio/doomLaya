import copy,unittest
from doomlib.enemy_commitment import EnemyCommitment,with_enemy_commitment,recorded_facts

class EnemyCommitmentTest(unittest.TestCase):
    def test_only_accepted_model_targets_change_history(self):
        h=EnemyCommitment()
        h.accept(dict(action='attack',target={'id':98}),10)
        h.accept(dict(action='attack',target={'id':98}),20)
        self.assertEqual(h.facts(45),dict(target_id=98,age_seconds=1.0))
        h.accept(dict(action='attack',target={'id':96}),45)
        self.assertEqual(h.facts(45),dict(target_id=96,age_seconds=0.0))
        h.accept(dict(action='pickup',target={'id':96}),46)
        self.assertEqual(h.facts(46),dict(target_id=None,age_seconds=None))
        h.accept(dict(action='attack',target={'id':96}),50);h.reset()
        self.assertIsNone(h.facts(51)['target_id'])

    def test_latest_acceptance_is_distinct_from_last_execution(self):
        p=dict(state='Unchanged',observation={'execution':{'target_id':1}},targets={'enemy':{'1':{'id':1},'2':{'id':2}}},
               questions={'enemy':dict(type='choice',instructions='Choose.',criteria={'1':'Visible enemy 1','2':'Not visible enemy 2'}),'command':{'unchanged':True}})
        original=copy.deepcopy(p);r=with_enemy_commitment(p,dict(target_id=2,age_seconds=0.0))
        self.assertEqual(p,original);self.assertEqual(r['state'],p['state']);self.assertEqual(r['targets'],p['targets'])
        self.assertEqual(r['questions']['command'],p['questions']['command'])
        self.assertTrue(r['questions']['enemy']['criteria']['2'].startswith('Latest accepted attack target: yes.'))
        self.assertTrue(r['questions']['enemy']['criteria']['1'].startswith('Latest accepted attack target: no.'))

    def test_absent_target_is_not_reintroduced(self):
        p=dict(questions={'enemy':dict(instructions='Choose.',criteria={'3':'Enemy 3'})},targets={'enemy':{'3':{'id':3}}})
        r=with_enemy_commitment(p,dict(target_id=98,age_seconds=.5))
        self.assertEqual(list(r['questions']['enemy']['criteria']),['3'])
        self.assertNotIn('98',str(r['targets']))


    def test_reconstruction_includes_just_accepted_but_excludes_future_response(self):
        def row(identifier,request,accepted,enemy,episode=0):
            return dict(tick=request,game_seconds=accepted/35,episode=episode,applied=True,directive=dict(action='attack',target={'id':enemy},decision_id=identifier))
        rows=[row(1,0,18,98),row(2,18,36,96),row(3,36,54,53),row(4,60,78,10,1)]
        facts=recorded_facts(rows)
        self.assertEqual(facts[1],dict(target_id=None,age_seconds=None))
        self.assertEqual(facts[2],dict(target_id=98,age_seconds=0.0))
        self.assertEqual(facts[3],dict(target_id=96,age_seconds=0.0))
        self.assertEqual(facts[4],dict(target_id=None,age_seconds=None))
