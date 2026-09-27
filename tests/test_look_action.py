"""Explicit view acquisition and observed damage, without automatic combat."""
import copy
import unittest
from tests.test_authority import SAMPLE,Motor,Exit
from doomlib.executor import Executor
from doomlib.look_questions import DamageHistory,with_look_action


class LookActionTest(unittest.TestCase):
    def motor(self):
        state=copy.deepcopy(SAMPLE);state['door']=None;state['angle']=20
        controller=Executor(mission=Exit());controller.navigator=Motor();controller.observe(state,0)
        return controller,state

    def test_turn_requires_model_and_stops_at_one_half_turn(self):
        controller,state=self.motor()
        self.assertFalse(any(controller.act(state,0)[0][:7]))
        for tick in range(24):
            if tick in (0,10,20):
                controller.accept(dict(action='look_back',command='look_back',target=None,weapon=None,decision_id=tick+1,expires_tick=30),tick)
            buttons,refs=controller.act(state,tick)
            self.assertFalse(any(buttons[:4]+buttons[5:7]))
            self.assertGreaterEqual(buttons[4],0)
            state['angle']=(state['angle']-buttons[4])%360
        self.assertAlmostEqual(state['angle'],200)
        self.assertEqual(state['execution']['status'],'arrived')
        self.assertEqual(buttons[4],0)

    def test_new_command_or_expiry_stops_turn(self):
        for interrupt in ('wait','expired'):
            controller,state=self.motor()
            controller.accept(dict(action='look_back',command='look_back',target=None,weapon=None,decision_id=1,expires_tick=2),0)
            self.assertGreater(controller.act(state,0)[0][4],0)
            if interrupt=='wait':controller.accept(dict(action='wait',command='wait',target=None,weapon=None,decision_id=2),1)
            self.assertFalse(any(controller.act(state,3)[0]))

    def test_damage_window_healing_and_episode_reset(self):
        history=DamageHistory();state={'hp':100,'execution':{}}
        self.assertEqual(history.observe(state,0,0)['hp_loss'],0)
        state['hp']=91;facts=history.observe(state,1,0)
        self.assertEqual(facts['hp_loss'],9)
        self.assertFalse(facts['looked_after_hit'])
        state['execution']={'action':'look_back','status':'arrived'}
        self.assertTrue(history.observe(state,5,0)['looked_after_hit'])
        state['hp']=80
        self.assertFalse(history.observe(state,6,0)['looked_after_hit'])
        state['hp']=90;self.assertEqual(history.observe(state,7,0)['hp_loss'],20)
        self.assertEqual(history.observe(state,77,0)['hp_loss'],0)
        state['hp']=100;self.assertEqual(history.observe(state,78,1)['hp_loss'],0)

    def test_question_keeps_choices_and_other_heads_unchanged(self):
        packet={'state':'HP 91; armor 0.','questions':{'command':{'instructions':'Choose.','criteria':{'wait':'Wait.'}},'weapon':{'criteria':{'keep':'Keep.'}}},'commands':{'wait':{'action':'wait','target':None}},'observation':{'execution':{}}}
        before=copy.deepcopy(packet)
        result=with_look_action(packet,{'hp_loss':9,'latest_age_seconds':.2,'looked_after_hit':False})
        self.assertEqual(packet,before)
        self.assertEqual(result['state'],before['state'])
        self.assertEqual(result['questions']['weapon'],before['questions']['weapon'])
        self.assertIn('look_back',result['commands'])
        self.assertEqual(result['questions']['command']['criteria']['wait'],'Wait.')
        self.assertIn('9 HP',result['questions']['command']['instructions'])
