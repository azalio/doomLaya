import copy
import unittest
from training.route_resupply import labels
from tests import test_map3_resource_training as resources


class ResupplyLabelsTests(unittest.TestCase):
    def packet(self, name, category, shells=10):
        p=resources.ResourceLabelsTest().packet(hp=100,shells=shells,name=name,category=category)
        p['targets']['item']['1']['distance']=7
        p['targets']['enemy']={}
        return p

    def test_loaded_shotgun_does_not_hide_unowned_super_shotgun(self):
        p=self.packet('SuperShotgun','Weapon');p['observation']['inventory']['8']=dict(owned=0,ammo=10)
        before=copy.deepcopy(p)
        self.assertIn(('item','1','route_weapon'),labels(p))
        self.assertEqual(p,before)

    def test_shell_resupply_before_gun_is_nearly_empty(self):
        p=self.packet('Shell','Ammo',shells=10)
        self.assertIn(('item','1','route_ammo'),labels(p))
        p['observation']['inventory']['3']['ammo']=20
        self.assertFalse(any(k=='item' for k,_,_ in labels(p)))

    def test_full_health_does_not_collect_a_stimpack(self):
        p=self.packet('Stimpack','Health')
        self.assertFalse(any(k=='item' for k,_,_ in labels(p)))

    def test_near_fight_precedes_nonurgent_supply(self):
        p=self.packet('Shell','Ammo');p['targets']['enemy']={'e':dict(distance=15,visible=True)}
        p['questions']['command']['criteria']['attack']='Fight'
        self.assertEqual(labels(p)[0][1],'attack')
        p['targets']['enemy']['e']['distance']=30
        self.assertEqual(labels(p)[0][1],'pickup')
