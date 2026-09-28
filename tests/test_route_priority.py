import copy
import unittest
from training.route_priority import labels
from tests import test_map3_resource_training as resources


class RoutePriorityTest(unittest.TestCase):
    def test_full_health_and_distant_weapon_do_not_delay_route(self):
        p=resources.ResourceLabelsTest().packet(hp=100,name='Shotgun',category='Weapon')
        p['targets']['item']['1']['distance']=36
        p['observation']['inventory']['3']['owned']=0
        original=copy.deepcopy(p)
        self.assertEqual(labels(p)[0][1],'use_switch')
        self.assertEqual(p,original)

    def test_bullets_with_loaded_shotgun_do_not_delay_route(self):
        p=resources.ResourceLabelsTest().packet(hp=86,shells=8,name='Clip',category='Ammo')
        p['observation']['inventory']['2']['ammo']=36
        self.assertEqual(labels(p)[0][1],'use_switch')

    def test_urgent_medikit_still_interrupts_fight(self):
        p=resources.ResourceLabelsTest().packet(hp=20,name='Medikit',category='Health')
        p['targets']['enemy']={'e':dict(distance=5,visible=True)}
        p['questions']['command']['criteria']['attack']='Fight'
        self.assertEqual(labels(p)[0][1],'pickup')

    def test_visible_fight_precedes_distant_key(self):
        p=resources.ResourceLabelsTest().packet(hp=86,shells=8,name='YellowCard',category='Key')
        p['targets']['enemy']={'e':dict(distance=25,visible=True)}
        p['questions']['command']['criteria']['attack']='Fight'
        self.assertEqual(labels(p)[0][1],'attack')

    def test_missing_key_remains_pickup_without_a_visible_threat(self):
        p=resources.ResourceLabelsTest().packet(hp=86,shells=8,name='YellowCard',category='Key')
        p['targets']['item']['1']['distance']=45
        self.assertEqual(labels(p)[:2],[('command','pickup','route_missing_key'),('item','1','route_key')])

    def test_exit_platform_is_activated_before_exiting_with_all_keys(self):
        p=resources.ResourceLabelsTest().packet()
        p['state']='HP 100; armor 0.\nCollected keys: blue, red, yellow.'
        p['targets']['switch']['2'].update(route_exit=True,activated=False)
        self.assertEqual(labels(p)[0][1],'use_switch')
        p['targets']['switch']['2']['activated']=True
        self.assertEqual(labels(p)[0][1],'exit')

    def test_blocking_door_is_a_prerequisite_to_health(self):
        p=resources.ResourceLabelsTest().packet(hp=20,name='Medikit',category='Health')
        p['observation']['execution']=dict(detail='A closed door blocks movement; choose open_door')
        self.assertEqual(labels(p)[0][1],'open_door')


if __name__=='__main__':unittest.main()
