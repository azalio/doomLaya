"""Inventory events request a model decision without choosing a weapon."""
import copy
import unittest
from decision_timing import inventory_signature,request_reason


class DecisionTimingTest(unittest.TestCase):
    def state(self):return dict(hp=100,keys=[],inventory={'2':dict(owned=1,ammo=50),'3':dict(owned=0,ammo=0)})

    def test_new_weapon_requests_an_early_decision(self):
        state=self.state();before=inventory_signature(state);state['inventory']['3'].update(owned=1,ammo=8)
        after=inventory_signature(state)
        self.assertEqual(request_reason(3,0,26,after,before,True),'inventory_changed')
        self.assertIsNone(request_reason(3,0,26,after,before,False))
        self.assertIsNone(request_reason(4,3,26,after,after,True))
        self.assertNotIn('execution',state)

    def test_ammo_consumption_and_damage_do_not_flood_the_api(self):
        state=self.state();before=inventory_signature(state);state['inventory']['2']['ammo']-=1;state['hp']-=20
        self.assertEqual(before,inventory_signature(state))
        self.assertIsNone(request_reason(3,0,26,inventory_signature(state),before,True))
        self.assertEqual(request_reason(26,0,26,inventory_signature(state),before,True),'interval')

    def test_ammo_events_track_shooting_availability_without_selecting_a_gun(self):
        state=self.state();state['inventory']['3'].update(owned=1,ammo=0)
        state['inventory']['8']=dict(owned=1,ammo=0)
        original=copy.deepcopy(state)
        empty=inventory_signature(state,include_ammo=True)
        state['inventory']['3']['ammo']=state['inventory']['8']['ammo']=1
        single=inventory_signature(state,include_ammo=True)
        self.assertNotEqual(empty,single)
        self.assertEqual(request_reason(3,0,26,single,empty,True),'inventory_changed')
        self.assertEqual(inventory_signature(state),inventory_signature(original))
        state['inventory']['3']['ammo']=state['inventory']['8']['ammo']=2
        double=inventory_signature(state,include_ammo=True)
        self.assertNotEqual(single,double)
        state['inventory']['3']['ammo']=state['inventory']['8']['ammo']=20
        self.assertEqual(double,inventory_signature(state,include_ammo=True))
        state['inventory']['3']['ammo']=state['inventory']['8']['ammo']=0
        self.assertEqual(empty,inventory_signature(state,include_ammo=True))
        self.assertNotIn('execution',state)

    def test_key_and_episode_changes_are_observed(self):
        state=self.state();before=inventory_signature(state);state['keys']=['red']
        self.assertEqual(request_reason(3,0,26,inventory_signature(state),before,True),'inventory_changed')
        self.assertNotEqual(inventory_signature(state,0),inventory_signature(state,1))


if __name__=='__main__':unittest.main()
