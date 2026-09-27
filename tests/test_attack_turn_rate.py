import unittest
from doomlib.executor import Executor

def state():
    return dict(x=0,y=0,angle=0,hp=100,weapon=3,ammo=10,walls=dict(left=10,right=10),
                enemies=[dict(id=1,bearing=70,aim_bearing=70,distance=10,visible=True)],
                inventory={'3':{'owned':1,'ammo':10}})

class AttackTurnRateTest(unittest.TestCase):
    def test_only_explicit_target_is_aimed_at_with_selected_motor_limit(self):
        for rate in (9,18,36):
            e=Executor(attack_turn_rate=rate);s=state()
            d=dict(action='attack',target={'id':1,'name':'Enemy'},weapon=3,movement='strafe_left',decision_id=1,command='attack',expires_tick=70)
            e.accept(d,0);buttons,_=e.act(s,0)
            self.assertEqual(buttons[4],rate);self.assertEqual(buttons[5],0);self.assertEqual(buttons[2],1)
            s=state();s['enemies'][0]['id']=2
            buttons,_=e.act(s,1)
            self.assertEqual(buttons[4:6],[0,0]);self.assertEqual(s['execution']['target_id'],1)

    def test_turn_limit_does_not_change_look_command_or_expiry(self):
        e=Executor(attack_turn_rate=36);s=state()
        e.accept(dict(action='look_back',target=None,weapon=3,decision_id=1,command='look_back',expires_tick=1),0)
        buttons,_=e.act(s,0);self.assertEqual(buttons[4],9)
        buttons,_=e.act(state(),2);self.assertFalse(any(buttons))

    def test_invalid_motor_settings_are_rejected(self):
        for value in (0,-9,90,float('nan')):
            with self.assertRaises(ValueError):Executor(attack_turn_rate=value)
