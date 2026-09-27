"""Offline supervision boundaries for useful resources and physical prerequisites."""
import unittest
from types import SimpleNamespace
from training.build_map3_resources import labels,candidates


class ResourceLabelsTest(unittest.TestCase):
    def packet(self, hp=100, shells=40, name='Shell', category='Ammo'):
        inventory={str(i):dict(owned=int(i in (1,2,3)),ammo=0 if i in (1,9) else shells if i in (3,8) else 100) for i in range(1,10)}
        return dict(state='HP '+str(hp)+'; armor 0.\nCollected keys: blue.',observation=dict(hp=hp,armor=0,inventory=inventory,execution={}),questions={'command':{'criteria':dict(pickup='',attack='',open_door='',use_switch='',exit='',explore='')},'weapon':{'criteria':{'shotgun':''}}},targets=dict(item={'1':dict(name=name,category=category,distance=3,reachable=True)},switch={'2':dict(kind='door',distance=10)},enemy={}),commands={},weapons={'shotgun':3})

    def test_sufficient_ammo_continues_the_route(self):
        packet=self.packet()
        self.assertEqual(candidates(packet)[0],[])
        self.assertEqual(labels(packet),[('command','use_switch','continue_route')])

    def test_health_bonus_at_full_health_does_not_interrupt_the_route(self):
        packet=self.packet(name='HealthBonus',category='Health')
        self.assertEqual(labels(packet),[('command','use_switch','continue_route')])

    def test_loaded_gun_fights_nearby_threat_before_resupplying(self):
        packet=self.packet(shells=5)
        packet['targets']['enemy']={'3':dict(distance=4)}
        self.assertEqual(labels(packet)[0],('command','attack','nearby_threat'))

    def test_blocked_healing_opens_the_door_before_collecting(self):
        packet=self.packet(hp=20,name='Medikit',category='Health')
        packet['observation']['execution']=dict(detail='A closed door blocks movement; choose open_door to open it')
        packet['commands']['open_door']=dict(target=dict(distance=2))
        self.assertEqual(labels(packet)[0],('command','open_door','blocked_door_prerequisite'))
        from training.map3_teacher import labels as teacher_labels
        packet['targets']['switch']={}
        state=dict(packet['observation'],keys=[])
        navigator=SimpleNamespace(movement_clearance=lambda state:dict(left=6,right=6,back=6))
        controller=SimpleNamespace(navigator=navigator,reachable_cache=(None,set()),mission=SimpleNamespace(data=dict(exits=[])))
        self.assertEqual(teacher_labels(packet,state,controller)['command'],'open_door')

    def test_unreachable_health_is_not_a_valid_pickup(self):
        packet=self.packet(hp=20,name='Medikit',category='Health')
        packet['targets']['item']['1']['reachable']=False
        self.assertEqual(labels(packet),[('command','use_switch','continue_route')])
