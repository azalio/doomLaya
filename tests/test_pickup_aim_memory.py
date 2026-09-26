"""Keep aiming at the model-selected enemy while recent memory is available."""
import copy
import unittest
from doomlib.executor import Executor
from tests.test_authority import SAMPLE,Motor,Exit


class PickupAimMemoryTest(unittest.TestCase):
    def setup_case(self):
        s=copy.deepcopy(SAMPLE);s['door']=None;s['weapon']=3;s['ammo']=10
        item=dict(s['items'][0],distance=8)
        enemy=dict(s['enemies'][0],distance=4,bearing=30,aim_bearing=30,visible=True)
        s['enemies']=[enemy]
        c=Executor(mission=Exit());c.navigator=Motor()
        c.navigator.steering_target=(item['x'],item['y'])
        c.observe(s,0);c.known[item['id']]=item
        c.accept(dict(action='pickup',target=item,combat_target=enemy,weapon=3,decision_id=1,command='pickup'),0)
        return c,s,item,enemy

    def test_temporary_loss_of_visibility_keeps_aim_but_suppresses_fire(self):
        c,s,item,enemy=self.setup_case()
        s['enemies']=[dict(enemy,visible=False)]
        buttons,refs=c.act(s,1)
        self.assertEqual(buttons[4],9)
        self.assertEqual(buttons[5],0)
        self.assertIn('aim_secondary_model_enemy',refs)
        self.assertFalse(s['combat']['target_visible'])
        self.assertEqual(s['execution']['target_id'],item['id'])
        self.assertEqual(s['execution']['combat_target_id'],enemy['id'])
        s['enemies']=[dict(enemy,visible=True,bearing=0,aim_bearing=0)]
        self.assertEqual(c.act(s,2)[0][5],1)

    def test_optional_recent_targets_are_chosen_by_the_model(self):
        from doomlib.policy import request
        from doomlib.decision_questions import factorize,with_pickup_combat,decode
        _,s,item,enemy=self.setup_case()
        s['enemies']=[dict(enemy,visible=False)]
        flat=request(s,{item['id']:item},Exit())
        original=with_pickup_combat(factorize(copy.deepcopy(flat)))
        self.assertEqual(set(original['questions']['combat']['criteria']),{'hold'})
        packet=with_pickup_combat(factorize(flat),include_recent=True)
        enemy_id=str(enemy['id'])
        self.assertEqual(set(packet['questions']['combat']['criteria']),{'hold',enemy_id})
        self.assertIn('last seen',packet['questions']['combat']['criteria'][enemy_id])
        answers={key:{'choice':value} for key,value in dict(command='pickup',item=str(item['id']),weapon='shotgun',combat=enemy_id).items()}
        selected=decode({'answers':answers},packet,12)
        self.assertEqual(selected['combat_target']['id'],enemy['id'])
        answers['combat']['choice']='hold'
        self.assertIsNone(decode({'answers':answers},packet,13)['combat_target'])

    def test_expired_enemy_memory_does_not_create_an_invisible_target(self):
        c,s,_,_=self.setup_case();s['enemies']=[]
        buttons,refs=c.act(s,1)
        self.assertEqual(buttons[4],0)
        self.assertEqual(buttons[5],0)
        self.assertNotIn('aim_secondary_model_enemy',refs)


if __name__=='__main__':unittest.main()
