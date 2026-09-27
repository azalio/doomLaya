"""Offline MAP03 supervision must respect resource and physical preconditions."""
import unittest
from training.build_map3_survival import label


class Map03TrainingTest(unittest.TestCase):
    def packet(self, enemy=10, shells=0, door=None, weapon_distance=4):
        inventory = {str(i): dict(owned=0,ammo=0) for i in range(1,10)}
        inventory['2'] = dict(owned=1,ammo=50)
        inventory['3'] = dict(owned=int(shells>0),ammo=shells)
        result = dict(questions={'command': {'criteria': {'pickup':'', 'attack':'', 'open_door':'', 'use_switch':''}}}, observation=dict(inventory=inventory,hp=100), targets=dict(enemy={} if enemy is None else {'1':dict(distance=enemy)}, item={'2':dict(name='Shotgun',category='Weapon',distance=weapon_distance,reachable=True)}), commands={})
        if door is not None:
            result['commands']['open_door'] = {'target':dict(distance=door,locked=False)}
        return result

    def test_get_a_loaded_weapon_before_a_distant_mechanism(self):
        self.assertEqual(label(self.packet()), ('pickup','loaded_weapon_before_route'))

    def test_loaded_shotgun_does_not_trigger_another_upgrade(self):
        self.assertEqual(label(self.packet(shells=8)), ('attack','nearby_enemy'))

    def test_open_a_blocking_door_before_routing_to_a_gun(self):
        self.assertEqual(label(self.packet(door=2)), ('open_door','blocking_door'))

    def test_fight_an_immediate_threat_before_a_distant_gun(self):
        self.assertEqual(label(self.packet(enemy=2)), ('attack','nearby_enemy'))

    def test_empty_owned_shotgun_can_be_resupplied(self):
        packet = self.packet(enemy=None)
        packet['observation']['inventory']['3']['owned'] = 1
        self.assertEqual(label(packet), ('pickup','loaded_weapon_before_route'))

    def test_leave_unrelated_navigation_unlabelled(self):
        self.assertIsNone(label(self.packet(enemy=None,weapon_distance=25)))


class Map03RouteTrainingTest(unittest.TestCase):
    def packet(self):
        packet = Map03TrainingTest().packet(enemy=None,shells=50)
        packet['state'] = 'Collected keys: blue.\nInventory: pistol 120 ammo; shotgun 50 ammo.'
        packet['targets']['item']['2'].update(name='Shell',category='Ammo')
        packet['targets']['switch'] = {'3':dict(kind='lift',route_keys=['red'],locked=False,activated=False)}
        return packet

    def test_sufficient_ammo_does_not_interrupt_the_key_route(self):
        from training.build_map3_route_recovery import label
        self.assertEqual(label(self.packet()), ('use_switch','continue_route_with_supplies'))

    def test_open_the_door_at_the_executor_blocking_distance(self):
        from training.build_map3_route_recovery import label
        packet=self.packet()
        packet['commands']['open_door']={'target':dict(distance=2.6,locked=False)}
        self.assertEqual(label(packet), ('open_door','blocking_door'))

    def test_ammo_augmentation_changes_counts_and_preserves_the_source(self):
        from training.build_map3_route_recovery import sufficient_ammo
        packet=self.packet();changed=sufficient_ammo(packet)
        self.assertEqual(packet['observation']['inventory']['3']['ammo'],50)
        self.assertEqual(changed['observation']['inventory']['3']['ammo'],40)
        self.assertEqual(changed['observation']['inventory']['8']['ammo'],40)
        self.assertIn('shotgun 40 ammo',changed['state'])
