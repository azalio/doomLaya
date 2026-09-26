"""Secondary combat follows an explicit model choice during navigation."""
import unittest
from decision_questions import factorize,with_navigation_combat,dependencies,decode
from policy import request
import test_pickup_aim_memory
from test_authority import Exit


class NavigationCombatTest(unittest.TestCase):
    def setup_case(self):
        return test_pickup_aim_memory.PickupAimMemoryTest().setup_case()

    def test_switch_exit_and_door_require_a_model_combat_answer(self):
        _,s,item,enemy=self.setup_case()
        switch=dict(id=728,name='Lift',activated=False,locked=False,distance=8,kind='lift',phase='call',approach=[0,0],board=[0,0])
        door=dict(id=137,x=0,y=0,distance=8,bearing=0,locked=False)
        s['switches']=[switch];s['door']=door
        packet=with_navigation_combat(factorize(request(s,{item['id']:item},Exit())),include_recent=True)
        for action in ('pickup','use_switch','open_door','exit','explore'):
            with self.subTest(action=action):
                self.assertIn('combat',dependencies(packet)[action])
                answers={k:{'choice':v} for k,v in dict(command=action,item=str(item['id']),switch='728',weapon='shotgun',combat=str(enemy['id'])).items()}
                selected=decode({'answers':answers},packet,10)
                self.assertEqual(selected['combat_target']['id'],enemy['id'])
                answers['combat']['choice']='hold'
                self.assertIsNone(decode({'answers':answers},packet,11)['combat_target'])
                del answers['combat']
                with self.assertRaises(KeyError):decode({'answers':answers},packet,12)
        self.assertNotIn('combat',dependencies(packet)['attack'])
        self.assertNotIn('combat',dependencies(packet)['wait'])

    def test_route_fire_keeps_switch_goal_and_honors_hold(self):
        c,s,_,enemy=self.setup_case();enemy=dict(enemy,bearing=0,aim_bearing=0)
        s['enemies']=[enemy]
        switch=dict(id=728,name='Lift',activated=False,locked=False,distance=8,phase='call',approach=[0,0],board=[0,0])
        s['switches']=[switch]
        command=dict(action='use_switch',target=switch,combat_target=enemy,weapon=3,decision_id=9,command='use_switch')
        c.accept(command,0);buttons,refs=c.act(s,0)
        self.assertEqual(buttons[5],1)
        self.assertIn('route_while_aiming_selected_enemy',refs)
        self.assertEqual(s['execution']['target_id'],728)
        self.assertEqual(s['execution']['combat_target_id'],enemy['id'])
        c.accept(dict(command,combat_target=None),1)
        self.assertEqual(c.act(s,1)[0][5],0)

    def test_switch_activation_keeps_its_aim_and_use(self):
        c,s,_,enemy=self.setup_case()
        switch=dict(id=728,name='Lift',activated=False,locked=False,distance=1,phase='call',x=s['x']+32,y=s['y'],approach=[s['x'],s['y']],board=[s['x'],s['y']])
        s['angle']=0;s['switches']=[switch]
        c.accept(dict(action='use_switch',target=switch,combat_target=enemy,weapon=3,decision_id=9,command='use_switch'),0)
        buttons,refs=c.act(s,0)
        self.assertIn('use_selected_switch',refs)
        self.assertNotIn('aim_secondary_model_enemy',refs)
        self.assertEqual(buttons[4],0)
        self.assertEqual(buttons[5],0)
        self.assertEqual(buttons[6],1)

    def test_lift_ride_can_fire_without_movement(self):
        c,s,_,enemy=self.setup_case();enemy=dict(enemy,bearing=0,aim_bearing=0)
        s['enemies']=[enemy]
        switch=dict(id=728,name='Lift',activated=False,locked=False,distance=1,phase='ride',approach=[0,0],board=[0,0])
        s['switches']=[switch]
        c.accept(dict(action='use_switch',target=switch,combat_target=enemy,weapon=3,decision_id=9,command='use_switch'),0)
        buttons,refs=c.act(s,0)
        self.assertEqual(buttons[:4],[0]*4)
        self.assertEqual(buttons[5],1)
        self.assertIn('ride_selected_lift',refs)


if __name__=='__main__':unittest.main()
