"""Resource observations remain factual and preserve model authority."""
import copy
import random
import unittest
from resource_questions import describe,with_resource_facts
from training.resource_augmentation import resource_facts,shuffle_and_rename


class ResourceQuestionsTest(unittest.TestCase):
    def observation(self):
        inv={str(i):dict(owned=int(i in (1,2,8)),ammo=7 if i in (3,8) else 60 if i in (2,4) else 0) for i in range(1,10)}
        return dict(hp=26,armor=105,inventory=inv)

    def test_shells_belong_to_the_super_shotgun_without_an_ordinary_shotgun(self):
        item=dict(name='Shell',category='Ammo',distance=3,reachable=True)
        self.assertIn('shells=7',describe(item,self.observation()))
        self.assertNotIn('60',describe(item,self.observation()))

    def test_descriptions_do_not_filter_unreachable_or_unneeded_items(self):
        items={'one':dict(name='Medikit',category='Health',distance=2,reachable=False),'two':dict(name='ArmorBonus',category='Armor',distance=3,reachable=True)}
        packet=dict(observation=self.observation(),targets={'item':items},commands={'pickup':{'action':'pickup','target':None}},questions={'item':dict(criteria={k:'old' for k in items}),'command':dict(criteria={'pickup':'Collect'})})
        before=copy.deepcopy(packet);result=with_resource_facts(packet)
        self.assertEqual(result['targets'],before['targets']);self.assertEqual(result['commands'],before['commands'])
        self.assertEqual(set(result['questions']['item']['criteria']),set(items));self.assertEqual(result['questions']['command'],before['questions']['command'])
        self.assertIn('unreachable',result['questions']['item']['criteria']['one'])
        self.assertIn('health=26',result['questions']['item']['criteria']['one'])
        self.assertIn('armor=105',result['questions']['item']['criteria']['two'])

    def test_legacy_rows_do_not_invent_ammo_when_the_gun_is_unowned(self):
        row=dict(kind='item',state='HP 26; armor 105.\nInventory: melee 0 ammo; pistol 60 ammo.',question=dict(criteria={'one':'Shotgun; reachable; not owned; 2.0m.'}))
        rendered=resource_facts(row)['question']['criteria']['one']
        item=dict(name='Shotgun',category='Weapon',distance=2,reachable=True);observed=self.observation();observed['inventory']['8']['owned']=0
        self.assertEqual(rendered,describe(item,observed));self.assertNotIn('shells=',rendered)

    def test_augmentation_preserves_the_semantic_answer_and_references(self):
        row=dict(kind='item',label='15',state='Current command: pickup #15.\nItems: Shotgun#15 and Medikit#16.',question=dict(criteria={'15':'Shotgun #15','16':'Medikit #16'}))
        original=copy.deepcopy(row);result=shuffle_and_rename(row,random.Random(92))
        label=result['label'];self.assertNotEqual(label,'15');self.assertIn('Shotgun #'+label,result['question']['criteria'][label]);self.assertIn('Shotgun#'+label,result['state']);self.assertEqual(row,original)


if __name__=='__main__':unittest.main()
