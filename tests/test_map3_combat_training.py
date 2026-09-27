"""Offline correction boundaries for visible targets and loaded weapons."""
import unittest
from training.build_map3_combat import gold


class CombatCorrectionTest(unittest.TestCase):
    def packet(self,enemies=None,shells=10,bullets=80):
        inventory={str(k):dict(owned=int(k in (1,2,3,4)),ammo=shells if k in (3,8) else bullets if k in (2,4) else 0) for k in range(1,10)}
        return dict(observation=dict(inventory=inventory),targets=dict(enemy=enemies or {}),questions=dict(weapon=dict(criteria={k:'' for k in ('melee','pistol','shotgun','chaingun','keep')})))

    def test_visible_shooter_takes_priority_over_an_old_position(self):
        p=self.packet({'1':dict(name='DoomImp',distance=4,visible=False),'2':dict(name='ShotgunGuy',distance=7,visible=True)})
        self.assertIn(('enemy','2','visible_threat'),gold(p))

    def test_point_blank_enemy_remains_an_immediate_threat(self):
        p=self.packet({'1':dict(name='Demon',distance=1,visible=False),'2':dict(name='ShotgunGuy',distance=7,visible=True)})
        self.assertIn(('enemy','1','visible_threat'),gold(p))

    def test_loaded_shotgun_priority_does_not_change_with_visibility(self):
        self.assertIn(('weapon','shotgun','shotgun_over_chaingun'),gold(self.packet()))
        self.assertIn(('weapon','shotgun','shotgun_over_chaingun'),gold(self.packet({'1':dict(name='DoomImp',distance=4,visible=True)})))

    def test_rapid_fire_curriculum_prefers_loaded_chaingun(self):
        self.assertIn(('weapon','chaingun','chaingun_over_shotgun'),gold(self.packet(),rapid_fire=True))
        p=self.packet();p['observation']['inventory']['4']['ammo']=0
        self.assertIn(('weapon','shotgun','shotgun'),gold(p,rapid_fire=True))

    def test_empty_shotgun_cannot_be_selected_over_a_loaded_chaingun(self):
        self.assertIn(('weapon','chaingun','chaingun'),gold(self.packet(shells=0)))
