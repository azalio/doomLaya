import copy
import unittest
from training.route_survival import labels
from training.route_priority import labels as original_labels
from tests import test_map3_resource_training as resources


class RouteSurvivalTests(unittest.TestCase):
    def packet(self):
        p=resources.ResourceLabelsTest().packet(hp=100,shells=0,name='Shotgun',category='Weapon')
        p['observation']['inventory']['3']['owned']=0
        p['observation']['inventory']['2'].update(owned=1,ammo=10)
        p['targets']['item']['1']['distance']=9
        p['targets']['enemy']={'e':dict(distance=15,visible=True)}
        p['questions']['command']['criteria']['attack']='Fight'
        return p

    def test_loaded_pistol_finishes_fight_before_walking_to_upgrade(self):
        p=self.packet();before=copy.deepcopy(p)
        self.assertEqual(original_labels(p)[0][1],'pickup')
        self.assertEqual(labels(p),[('command','attack','route_finish_fight_before_upgrade')])
        self.assertEqual(p,before)

    def test_empty_pistol_and_absent_threat_keep_weapon_pickup(self):
        p=self.packet();p['observation']['inventory']['2']['ammo']=0
        self.assertEqual(labels(p)[0][1],'pickup')
        p=self.packet();p['targets']['enemy']={}
        self.assertEqual(labels(p)[0][1],'pickup')

    def test_urgent_health_still_interrupts_fight(self):
        p=self.packet();p['observation']['hp']=20
        p['targets']['item']['1'].update(name='Medikit',category='Health',distance=3)
        self.assertEqual(labels(p)[0][1],'pickup')
