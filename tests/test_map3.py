"""MAP03 mechanisms and physical execution regressions."""
import unittest
from pathlib import Path
import vizdoom
from doomlib.mission import map_data


class Map03Test(unittest.TestCase):
    def test_remote_open_door_switches_are_available_to_the_model(self):
        data = map_data(Path(vizdoom.__file__).parent / 'freedoom2.wad', 'MAP03')
        switches = {s['id']: s for s in data['switches']}
        self.assertIn(1850, switches, 'The starting-area gate control is missing')
        self.assertEqual(switches[1850]['kind'], 'door')
        self.assertEqual(switches[1850]['sectors'], [34])
        self.assertIn(1455, switches, 'Repeatable remote door control is missing')
        self.assertEqual(switches[1455]['sectors'], [165])

    def test_selected_gate_opens_the_route_to_the_blue_key(self):
        import tempfile
        from diagnostics.probe_map03_gate import run_fixture
        with tempfile.TemporaryDirectory() as directory:
            result = run_fixture(directory)
        self.assertFalse(result['route_before'])
        self.assertIsNotNone(result['opened_tick'])
        self.assertLess(result['opened_tick'], 105)
        self.assertTrue(result['route_after'])
        self.assertEqual({r['execution']['target_id'] for r in result['history']}, {1850})

    def test_repeatable_door_control_is_available_after_the_door_closes(self):
        from types import SimpleNamespace
        from doomlib.mission import Mission
        data = map_data(Path(vizdoom.__file__).parent / 'freedoom2.wad', 'MAP03')
        control = next(s for s in data['switches'] if s['id'] == 1455)
        mission = Mission(dict(exits=[], switches=[control]))
        sectors = [SimpleNamespace(floor_height=0, ceiling_height=0) for _ in range(166)]
        state = dict(x=2400,y=-464,keys=[])
        mission.observe(state,sectors)
        self.assertFalse(state['switches'][0]['activated'])
        sectors[165].ceiling_height = 128
        mission.observe(state,sectors)
        self.assertTrue(state['switches'][0]['activated'])
        sectors[165].ceiling_height = 0
        mission.observe(state,sectors)
        self.assertFalse(state['switches'][0]['activated'])

    def test_once_only_control_stays_used_after_the_door_closes(self):
        from types import SimpleNamespace
        from doomlib.mission import Mission
        data = map_data(Path(vizdoom.__file__).parent / 'freedoom2.wad', 'MAP03')
        control = next(s for s in data['switches'] if s['id'] == 1850)
        mission = Mission(dict(exits=[], switches=[control]))
        mission.note_switch_use(1850,0)
        sectors = [SimpleNamespace(floor_height=0, ceiling_height=128) for _ in range(35)]
        state = dict(x=-400,y=400,keys=[])
        mission.observe(state,sectors)
        sectors[34].ceiling_height = 0
        mission.observe(state,sectors)
        self.assertTrue(state['switches'][0]['activated'])

    def test_exit_floor_switch_is_offered_before_the_floor_lowers(self):
        data = map_data(Path(vizdoom.__file__).parent / 'freedoom2.wad', 'MAP03')
        switches = {s['id']: s for s in data['switches']}
        self.assertIn(2839, switches, 'Exit platform lowering control is missing')
        self.assertEqual(switches[2839]['kind'], 'floor')
        self.assertEqual(switches[2839]['sectors'], [306])
        self.assertTrue(switches[2839]['route_exit'])

    def test_selected_floor_switch_opens_a_route_to_the_exit(self):
        import tempfile
        from diagnostics.probe_map03_floor import run_fixture
        with tempfile.TemporaryDirectory() as directory:
            result = run_fixture(directory)
        self.assertFalse(result['route_before'])
        self.assertIsNotNone(result['opened_tick'])
        self.assertLess(result['opened_tick'], 105)
        self.assertTrue(result['route_after'])
        self.assertEqual({r['execution']['target_id'] for r in result['history']}, {2839})

    def test_other_button_opening_a_shared_door_does_not_consume_an_unused_switch(self):
        from types import SimpleNamespace
        from doomlib.mission import Mission
        data=map_data(Path(vizdoom.__file__).parent/'freedoom2.wad','MAP03')
        controls=[s for s in data['switches'] if s['id'] in (1455,1863)]
        mission=Mission(dict(exits=[],switches=controls))
        sectors=[SimpleNamespace(floor_height=0,ceiling_height=0) for _ in range(166)]
        state=dict(x=2400,y=128,keys=[])
        sectors[165].ceiling_height=128
        mission.observe(state,sectors)
        sectors[165].ceiling_height=0
        mission.observe(state,sectors)
        self.assertFalse(next(s for s in state['switches'] if s['id']==1863)['activated'])

    def test_shared_door_reopens_from_the_second_button_after_crossing_trigger(self):
        import tempfile
        from diagnostics.probe_map03_shared_door import run_fixture
        with tempfile.TemporaryDirectory() as directory:
            result=run_fixture(directory)
        self.assertTrue(result['closed_again'])
        self.assertTrue(result['unused_second_button_available'])
        self.assertIsNotNone(result['reopened_tick'])
        self.assertTrue(result['route_after'])

    def test_selected_route_can_leave_a_descending_lift(self):
        import tempfile
        from diagnostics.probe_map03_descending_lift import run_fixture
        with tempfile.TemporaryDirectory() as directory:
            result=run_fixture(directory)
        self.assertIsNotNone(result['reached_tick'])
        self.assertLess(result['reached_tick'],175)
