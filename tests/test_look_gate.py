"""The learned look gate may add a turn, but cannot change regular action rankings."""
import copy,unittest
from doomlib.look_questions import with_look_gate,mix_look_answer,look_gate_input
from doomlib.question_heads import QuestionHeads

class GateStub:
    def __init__(self,p):self.p=p;self.calls=[]
    def predict(self,state,questions):
        self.calls.append((state,copy.deepcopy(questions)))
        return dict(model='laya',answers={k:dict(type='choice',probabilities=dict(self.p),choice=max(self.p,key=self.p.get),confidence=.9) for k in questions},usage={'input_tokens':11})

class LookGateTest(unittest.TestCase):
    def facts(self):return dict(hp_loss=9,latest_age_seconds=.2,looked_after_hit=False,status='inactive',known_enemy_count=0)

    def test_probabilities_preserve_old_rankings_and_expose_both_heads(self):
        base=dict(type='choice',choice='attack',probabilities={'attack':.7,'pickup':.3},confidence=.7)
        gate=dict(type='choice',choice='normal',probabilities={'normal':.99,'look_back':.01})
        result=mix_look_answer(base,gate,['attack','pickup','look_back'])
        self.assertAlmostEqual(sum(result['probabilities'].values()),1)
        self.assertEqual(result['choice'],'attack')
        self.assertAlmostEqual(result['probabilities']['attack']/result['probabilities']['pickup'],7/3)
        gate['probabilities']={'normal':.1,'look_back':.9}
        self.assertEqual(mix_look_answer(base,gate,['attack','pickup','look_back'])['choice'],'look_back')
        self.assertEqual(base['probabilities'],{'attack':.7,'pickup':.3})

    def test_routing_leaves_original_command_input_exact(self):
        base=GateStub({'attack':.7,'pickup':.3});gate=GateStub({'normal':.99,'look_back':.01})
        heads=QuestionHeads(base,{'look_gate':gate,'command':base},command_without_goal=True)
        original=dict(type='choice',instructions='Choose.',criteria={'attack':'Attack.','pickup':'Pick up.'})
        packet=dict(state='Current command: pickup\nHP 40.',questions={'command':original},commands={'attack':{},'pickup':{}},observation={'execution':{}},targets={'enemy':{}})
        result=with_look_gate(packet,self.facts());answer=heads.predict(result['state'],result['questions'])
        self.assertEqual(base.calls,[('HP 40.',{'command':original})])
        self.assertEqual(answer['answers']['command']['choice'],'attack')
        self.assertEqual(answer['usage']['input_tokens'],22)
        self.assertIn('Health lost recently: yes',gate.calls[0][0])
        self.assertNotIn('HP 40',gate.calls[0][0])
        self.assertNotIn('look_observation',packet['questions']['command'])

    def test_missing_gate_is_an_error_not_implicit_action_policy(self):
        base=GateStub({'attack':1})
        q=dict(type='choice',instructions='Choose.',criteria={'attack':'Attack','look_back':'Turn'},look_observation=self.facts())
        with self.assertRaises(ValueError):QuestionHeads(base,{}).predict('State',{'command':q})

    def test_compact_input_does_not_supply_an_unseen_attacker(self):
        state,q=look_gate_input(self.facts())
        self.assertIn('Known enemies: 0',state)
        self.assertEqual(set(q['criteria']),{'normal','look_back'})
        self.assertNotIn('target',state.lower())
