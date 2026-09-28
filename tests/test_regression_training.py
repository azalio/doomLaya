"""Regression supervision must preserve model choice and held-out provenance."""
import copy
import unittest
from training.build_regression_replay import resource_examples, project
from tests import test_map3_resource_training as resources


class RegressionTrainingTests(unittest.TestCase):
    def test_full_health_medikit_is_not_the_resource_label(self):
        packet=resources.ResourceLabelsTest().packet(hp=100,name='Medikit',category='Health')
        packet['targets']['item']['2']=dict(name='Shotgun',category='Weapon',distance=14,reachable=True)
        packet['observation']['inventory']['3']['owned']=0
        packet['questions']['item']=dict(type='choice',instructions='Choose item.',criteria={'1':'Medikit; reachable; 1.0m.','2':'Shotgun; reachable; not owned; 14.0m.'})
        packet['state']+='\nInventory: melee 0 ammo; pistol 50 ammo.\nItems: Medikit#1 [Health] 1.0m; Shotgun#2 [Weapon] 14.0m.'
        original=copy.deepcopy(packet)
        rows=resource_examples(packet,'regression',0,0)
        item=next(r for r in rows if r['kind']=='item')
        self.assertEqual(item['label'],'2')
        self.assertEqual(packet,original)
        projected=project(item)
        self.assertEqual(set(projected['question']['criteria']),{'1','2'})
        self.assertIn('Medikit',projected['question']['criteria']['1'])
        self.assertIn('HP 100',projected['state'])

    def test_reachable_missing_key_beats_completed_route_lifts(self):
        packet=resources.ResourceLabelsTest().packet(hp=86,shells=40,name='YellowCard',category='Key')
        packet['state']='HP 86; armor 90.\nCollected keys: blue, red.'
        packet['targets']['item']['1']['distance']=45
        packet['questions']['item']=dict(type='choice',instructions='Choose item.',criteria={'1':'YellowCard; reachable; 45.0m.'})
        rows=resource_examples(packet,'regression',35000,0)
        self.assertEqual({r['kind']:r['label'] for r in rows},{'command':'pickup','item':'1'})

    def test_command_projection_matches_server_and_keeps_world(self):
        row=dict(kind='command',state='Current command: pickup #1.\nHP 100; armor 0.',question=dict(type='choice',instructions='Finish the level alive.',criteria={'pickup':'Pick item.','exit':'Exit.','look_back':'Look.'},look_observation={}),label='exit')
        out=project(row)
        self.assertNotIn('Current command:',out['state'])
        self.assertIn('HP 100',out['state'])
        self.assertNotIn('look_back',out['question']['criteria'])
        self.assertIn('look_back',row['question']['criteria'])


if __name__=='__main__':unittest.main()
