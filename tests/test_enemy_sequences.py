"""A firing sequence is an explicit model choice, never controller ranking."""
import copy,itertools,unittest
from doomlib.enemy_sequences import with_enemy_sequences,advance_sequence
from doomlib.decision_questions import decode
from doomlib.executor import Executor
from tests.test_authority import SAMPLE,Motor,Exit

class EnemySequencesTest(unittest.TestCase):
    def packet(self):
        base=dict(SAMPLE['enemies'][0],aim_bearing=0,visible=True)
        targets={str(i):dict(base,id=i,distance=float(i),name='Zombieman') for i in (1,2,3)}
        return dict(decision_format='committed',commands={'attack':dict(action='attack',target=None)},weapons={'shotgun':3},questions={'enemy':dict(type='choice',instructions='Choose.',criteria={k:'Enemy' for k in targets})},targets={'enemy':targets},enemy_commitment={'target_id':2,'age_seconds':.3})

    def test_all_ordered_subsets_are_available_without_mutating_packet(self):
        p=self.packet();old=copy.deepcopy(p);q=with_enemy_sequences(p)
        wanted={order for n in (1,2,3) for order in itertools.permutations(p['targets']['enemy'],n)}
        self.assertEqual({tuple(v) for v in q['enemy_sequences'].values()},wanted)
        self.assertEqual(len(q['questions']['enemy']['criteria']),15)
        self.assertIn('Latest accepted target: #2',q['questions']['enemy']['instructions'])
        self.assertEqual(p,old)

    def test_decode_preserves_the_chosen_order_and_optional_short_plan(self):
        p=with_enemy_sequences(self.packet())
        for order in (['3','1','2'],['2']):
            key=next(k for k,v in p['enemy_sequences'].items() if v==order)
            result={'answers':{'command':{'choice':'attack'},'weapon':{'choice':'shotgun'},'enemy':{'choice':key},'movement':{'choice':'stationary'}}}
            d=decode(result,p,12)
            self.assertEqual([t['id'] for t in d['target_sequence']],list(map(int,order)))
            self.assertEqual(d['target']['id'],int(order[0]))

    def test_executor_skips_only_absent_members_and_never_adds_a_nearer_enemy(self):
        s=copy.deepcopy(SAMPLE);s['door']=None;p=self.packet();targets=p['targets']['enemy'];order=[targets[k] for k in ('3','1','2')]
        c=Executor(mission=Exit());c.navigator=Motor();c.observe(s,0)
        d=dict(action='attack',command='attack',target=order[0],target_sequence=order,weapon=None,decision_id=7,expires_tick=20)
        c.accept(d,0)
        for tick,present,expected in [(1,[1,2,3,99],3),(2,[1,2,99],1),(3,[2,3,99],2),(4,[99],None),(5,[1,2,3,99],None)]:
            s['enemies']=[dict(targets.get(str(i),targets['1']),id=i,aim_bearing=0,visible=True) for i in present]
            c.act(s,tick)
            self.assertEqual(s['execution']['target_id'],expected)
            self.assertEqual([v['id'] for v in c.directive['target_sequence']],[3,1,2])
        self.assertEqual(c.act(s,21)[0],[0.]*14)

    def test_legacy_single_target_does_not_change_when_missing(self):
        target=self.packet()['targets']['enemy']['2']
        self.assertEqual(advance_sequence({'target':target},[])[0],target)

    def test_invalid_plan_is_rejected(self):
        c=Executor();target=self.packet()['targets']['enemy']['1']
        for sequence in ([],[target,target]):
            with self.assertRaises(ValueError):c.accept(dict(action='attack',target=target,target_sequence=sequence,weapon=None,decision_id=1),0)

if __name__=='__main__':unittest.main()
