import unittest
from types import SimpleNamespace
from unittest.mock import patch
from doomlib.floor_hazards import FloorHazards
from doomlib.look_questions import look_gate_input,with_look_gate


def square(x1,y1,x2,y2):
    pts=[(x1,y1),(x2,y1),(x2,y2),(x1,y2),(x1,y1)]
    return [SimpleNamespace(x1=a,y1=b,x2=c,y2=d) for (a,b),(c,d) in zip(pts,pts[1:])]

class FloorFactsTest(unittest.TestCase):
    def test_damage_requires_floor_contact_and_preserves_interior_safe_island(self):
        sectors=[SimpleNamespace(floor_height=-8,lines=square(0,0,100,100)+square(40,40,60,60))]
        metadata=[dict(sector=0,special=7,damage_per_period=5,period_ticks=32,texture='NUKAGE1')]
        with patch('doomlib.floor_hazards.mapped_hazards',return_value=metadata):facts=FloorHazards('unused','MAP03',sectors)
        for x,y,z,expected in [(10,10,-8,True),(10,10,8,False),(50,50,-8,False),(120,10,-8,False)]:
            self.assertEqual(facts.observe(dict(x=x,y=y,z=z),sectors)['mapped_damaging_floor'],expected)
        sectors[0].floor_height=0
        self.assertFalse(facts.observe(dict(x=10,y=10,z=-8),sectors)['mapped_damaging_floor'])
        self.assertTrue(facts.observe(dict(x=10,y=10,z=0),sectors)['mapped_damaging_floor'])

    def test_floor_fact_is_only_model_input_and_does_not_mask_look_or_regular_actions(self):
        facts=dict(hp_loss=5,latest_age_seconds=.1,looked_after_hit=False,status='inactive',known_enemy_count=0)
        legacy,_=look_gate_input(facts)
        packet=dict(state='HP 20.',questions={'command':dict(type='choice',instructions='Choose.',criteria={'pickup':'Item','use_switch':'Switch'})},commands={'pickup':{},'use_switch':{}},observation={},targets={})
        enriched=dict(facts,standing_on_damaging_floor=True)
        state,_=look_gate_input(enriched)
        self.assertIn('Standing on a mapped damaging floor: yes.',state)
        result=with_look_gate(packet,enriched)
        self.assertEqual(result['state'],packet['state'])
        self.assertEqual(set(result['questions']['command']['criteria']),{'pickup','use_switch','look_back'})
        self.assertNotIn('damaging floor',legacy)
        with self.assertRaises(ValueError):look_gate_input(dict(facts,standing_on_damaging_floor='yes'))
