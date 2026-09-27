"""Optional observation memory preserves seen positions, never exposes unseen enemies."""
import unittest
from types import SimpleNamespace
from agent import Sensors


class EnemyMemoryTest(unittest.TestCase):
    def test_longer_memory_keeps_only_the_last_seen_position_then_expires(self):
        sensors=Sensors(enemy_memory_ticks=210)
        enemy=dict(id=5,name='Zombieman',x=32,y=64,z=0,distance=2.2,bearing=0)
        objects={5:SimpleNamespace(name='Zombieman',position_x=4000),6:SimpleNamespace(name='DoomImp',position_x=32)}
        sensors.remember_enemies([enemy],objects,0,0,0,0)
        remembered=sensors.remember_enemies([],objects,0,0,0,105)
        self.assertEqual([e['id'] for e in remembered],[5])
        self.assertEqual(remembered[0]['x'],32)
        self.assertFalse(remembered[0]['visible'])
        self.assertEqual(sensors.remember_enemies([],objects,0,0,0,211),[])

    def test_default_memory_still_expires_after_two_seconds(self):
        sensors=Sensors()
        enemy=dict(id=5,name='Zombieman',x=32,y=64,z=0,distance=2.2,bearing=0)
        objects={5:SimpleNamespace(name='Zombieman')}
        sensors.remember_enemies([enemy],objects,0,0,0,0)
        self.assertEqual(sensors.remember_enemies([],objects,0,0,0,71),[])
