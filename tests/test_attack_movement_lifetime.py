"""A target disappearing must not cancel an unexpired, explicit movement choice."""
import copy
import unittest
from doomlib.executor import Executor
from tests.test_authority import SAMPLE,Motor,Exit


class AttackMovementLifetimeTest(unittest.TestCase):
    def case(self, movement):
        state=copy.deepcopy(SAMPLE);state['door']=None
        target=dict(state['enemies'][0],aim_bearing=0)
        state['enemies']=[dict(target,id=target['id']+999)]
        controller=Executor(mission=Exit());controller.navigator=Motor();controller.observe(state,0)
        controller.accept(dict(action='attack',command='attack',target=target,weapon=None,movement=movement,decision_id=9,expires_tick=20),0)
        return controller,state,target

    def test_missing_target_keeps_only_the_requested_movement(self):
        for movement,index in [('strafe_left',2),('strafe_right',3),('backward',1)]:
            with self.subTest(movement=movement):
                controller,state,target=self.case(movement)
                buttons,_=controller.act(state,1)
                expected=[0.]*14;expected[index]=1
                self.assertEqual(buttons,expected)
                self.assertEqual(state['execution']['target_id'],target['id'])
                self.assertEqual(state['execution']['status'],'unavailable')

    def test_stationary_choice_does_not_acquire_implicit_movement(self):
        controller,state,_=self.case(None)
        self.assertEqual(controller.act(state,1)[0],[0.]*14)

    def test_expiry_stops_movement_even_when_target_is_missing(self):
        controller,state,_=self.case('strafe_left')
        self.assertEqual(controller.act(state,21)[0],[0.]*14)
