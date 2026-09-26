"""MAP02 regressions against engine geometry and observed level transitions."""
import math
import unittest
from pathlib import Path
from types import SimpleNamespace
import vizdoom
from agent import make_game, BUTTONS
from mission import map_data
from navigation import Navigator


class Map02Test(unittest.TestCase):
    def test_map02_to_map03_preserves_large_sector_geometry(self):
        import json
        import os
        import signal
        import subprocess
        import sys
        import tempfile
        code = """from types import SimpleNamespace
import json
from agent import make_game, BUTTONS
game=make_game(SimpleNamespace(map='MAP02',skill=3,seed=54,show=False,sound=False,weapon_sensor=True))
try:
    game.make_action([0]*len(BUTTONS),12)
    game.set_doom_map('MAP03')
    game.new_episode()
    game.make_action([0]*len(BUTTONS),117)
    state=game.get_state()
    print(json.dumps(dict(map=game.get_doom_map(),ticks=game.get_episode_time(),sectors=len(state.sectors),largest_sector=max(len(s.lines) for s in state.sectors))))
finally:game.close()
"""
        with tempfile.TemporaryFile(mode='w+') as log:
            child=subprocess.Popen([sys.executable,'-X','faulthandler','-c',code],stdout=log,stderr=log,start_new_session=True)
            try:
                result=child.wait(timeout=30)
            finally:
                try:os.killpg(child.pid,signal.SIGKILL)
                except ProcessLookupError:pass
            log.seek(0);output=log.read()
        self.assertEqual(result,0,output)
        state=json.loads(output.strip().splitlines()[-1])
        self.assertEqual(state['map'],'MAP03')
        self.assertGreaterEqual(state['ticks'],118)
        self.assertEqual(state['sectors'],315)
        self.assertEqual(state['largest_sector'],168)

    def test_selected_door_opens_from_the_corner_without_changing_target(self):
        import tempfile
        from diagnostics.probe_door_corner import run_fixture
        with tempfile.TemporaryDirectory() as directory:
            result=run_fixture(directory)
        self.assertIsNotNone(result['opened_tick'])
        self.assertLess(result['opened_tick'],105)
        self.assertGreaterEqual(result['height'],56)
        targets={row['execution']['target_id'] for row in result['history']}
        self.assertEqual(targets,{156})

    def test_selected_item_is_collected_from_the_correct_height(self):
        import tempfile
        from diagnostics.probe_pickup_ledge import run_fixture
        with tempfile.TemporaryDirectory() as directory:
            result=run_fixture(directory)
        self.assertTrue(result['initial_present'])
        self.assertIsNotNone(result['collected_tick'])
        self.assertLess(result['collected_tick'],140)
        self.assertFalse(result['history'][-1]['present'])
        self.assertGreater(result['history'][-1]['hp'],100)
        self.assertEqual(len({row['execution']['target_id'] for row in result['history']}),1)

    def test_cached_route_replans_after_falling_below_a_nearby_waypoint(self):
        game=make_game(SimpleNamespace(map='MAP02',skill=3,seed=54,show=False,sound=False),no_monsters=True)
        try:
            game.make_action([0]*len(BUTTONS),12)
            nav=Navigator(game.get_state().sectors)
            state=dict(x=822.18,y=-431.98,z=-32,angle=271.6,keys=[])
            target=(816,-496);goal=nav.nearest(target)
            nav.observe(state,0);nav.requested=('point',goal);nav.path=[goal]
            self.assertFalse(nav.clear_segment((state['x'],state['y']),nav.point(goal)))
            _,refs=nav.steer(state,1,target)
            self.assertIn('waypoint',refs)
            self.assertNotEqual(nav.steering_target,nav.point(goal))
            self.assertTrue(nav.clear_segment((state['x'],state['y']),nav.steering_target))
            self.assertIn(goal,nav.path)
        finally:game.close()

    def test_lift_key_routes_are_derived_without_selecting_a_goal(self):
        from executor import Executor
        from mission import Mission
        game=make_game(SimpleNamespace(map='MAP02',skill=3,seed=54,show=False,sound=False),no_monsters=True)
        try:
            game.make_action([0]*len(BUTTONS),12)
            mission=Mission(map_data(game.get_doom_game_path(),'MAP02'))
            controller=Executor(game.get_state().sectors,mission,mechanism_facts=True)
            routes={s['id']:s.get('route_keys') for s in mission.data['switches'] if s.get('kind')=='lift'}
            self.assertEqual(routes,{728:['red'],805:['blue']})
            self.assertIsNone(controller.directive)
        finally:game.close()

    def test_weapon_markers_include_only_single_player_map02_weapons(self):
        import pathlib,vizdoom
        from mission import map_data
        data=map_data(pathlib.Path(vizdoom.__file__).parent/'freedoom2.wad','MAP02',3)
        self.assertEqual(sorted(i['name'] for i in data['weapon_markers']),['Shotgun','Shotgun','SuperShotgun'])
        self.assertIn((352,-864),[(i['x'],i['y']) for i in data['weapon_markers'] if i['name']=='SuperShotgun'])

    def test_key_pickup_event_preserves_item_name(self):
        import io,json
        from agent import emit_event
        from functools import partial
        handle=io.StringIO();event=partial(emit_event,handle)
        event('key_pickup',35,id=27,color='blue',name='BlueCard')
        self.assertEqual(json.loads(handle.getvalue()),dict(event='key_pickup',game_seconds=1.,id=27,color='blue',name='BlueCard'))

    def test_stair_route_accounts_for_player_radius(self):
        game=make_game(SimpleNamespace(map='MAP02',skill=3,seed=48,show=False,sound=False))
        try:
            game.make_action([0]*len(BUTTONS),12)
            nav=Navigator(game.get_state().sectors)
            self.assertFalse(nav.clear_segment((696,-216),(696,-168)))
            self.assertTrue(nav.clear_segment((680,-216),(680,-168)))
            nav.plan({'x':696,'y':-248},0,(696,-120))
            self.assertTrue(nav.path)
            self.assertTrue(any(nav.point(node)[0]<690 for node in nav.path))
        finally:game.close()

    def test_route_can_descend_to_yellow_key(self):
        game = make_game(SimpleNamespace(map='MAP02', skill=3, seed=48, show=False, sound=False))
        try:
            game.make_action([0] * len(BUTTONS), 12)
            nav = Navigator(game.get_state().sectors)
            nav.plan({'x': 640, 'y': -576}, 0, (-256, 800))
            self.assertFalse(nav.exhausted, 'The walkable drop to the yellow key is rejected')
            self.assertTrue(nav.path)
            self.assertTrue(any(nav.floors[b] - nav.floors[a] < -64 for a, b in zip(nav.path, nav.path[1:])))
        finally:
            game.close()

    def test_completion_requires_the_requested_map_and_real_next_spawn(self):
        from diagnostics.verify_model_run import level_completion
        config={'args':{'map':'MAP02'}}
        finish={'event':'level_finished','map':'MAP02','alive':True,'engine_finished':True,'game_seconds':60}
        spawn={'event':'episode_started','map':'MAP03','engine_map':'MAP03','episode':1,'game_seconds':60}
        rows=[{'map':'MAP03','episode':1,'engine_tic':12+i,'seconds':60+i/35} for i in range(105)]
        self.assertTrue(level_completion(config,[finish,spawn],rows))
        self.assertFalse(level_completion(config,[finish,spawn],rows[:104]))
        self.assertFalse(level_completion(config,[finish,dict(spawn,engine_map='MAP02')],rows))
        self.assertFalse(level_completion(config,[dict(finish,map='MAP01'),spawn],rows))
        self.assertFalse(level_completion(config,[finish,dict(spawn,game_seconds=40)],rows))

    def test_collected_yellow_key_allows_exit_route_through_teleport(self):
        game=make_game(SimpleNamespace(map='MAP02',skill=3,seed=48,show=False,sound=False))
        try:
            game.make_action([0]*len(BUTTONS),12)
            data=map_data(Path(vizdoom.__file__).parent/'freedoom2.wad','MAP02')
            doors=data['doors']+[{'sector':i,'key':None} for switch in data['switches'] for i in switch['sectors']]
            nav=Navigator(game.get_state().sectors,doors,data['teleports'])
            state={'x':-256,'y':800,'keys':['yellow']}
            nav.observe(state,0)
            nav.plan(state,0,(104,-320))
            self.assertTrue(nav.path)
            self.assertTrue(any(a in nav.portal_edges and nav.portal_edges[a][0]==b for a,b in zip(nav.path,nav.path[1:])))
            nav.observe(dict(state,keys=[]),1)
            nav.plan(state,1,(104,-320))
            self.assertTrue(nav.exhausted)
        finally:
            game.close()

    def test_explore_searches_unvisited_cells_inside_a_known_region(self):
        nav=Navigator();nav.free={(x,0) for x in range(15)}
        nav.floors={node:0 for node in nav.free};nav.regions[(0,0)]=1;nav.entered={(0,0)}
        nav.plan({'x':8,'y':8},0)
        self.assertTrue(nav.path)
        self.assertEqual(nav.goal_kind,'new_cell')

    def test_teleport_discards_waypoints_before_the_jump(self):
        nav=Navigator();nav.free={(0,0),(100,0)};nav.floors={k:0 for k in nav.free}
        nav.observe({'x':8,'y':8},0)
        nav.path=[(0,0),(100,0)]
        nav.observe({'x':1608,'y':8},1)
        self.assertEqual(nav.path,[])

    def test_lift_can_be_called_again_after_returning_to_lower_floor(self):
        from mission import Mission
        line=SimpleNamespace(x1=0,y1=0,x2=128,y2=128)
        sector=SimpleNamespace(lines=[line],floor_height=96,ceiling_height=224)
        lift=dict(id=728,kind='lift',sectors=[0],upper_floor=96,x=64,y=0,key=None)
        mission=Mission(dict(exits=[],switches=[lift]))
        mission.lowered_lifts.add(728)
        top=dict(x=64,y=64,z=96,keys=[])
        mission.observe(top,[sector])
        self.assertTrue(top['switches'][0]['activated'])
        bottom=dict(x=64,y=-40,z=0,keys=[])
        mission.observe(bottom,[sector])
        self.assertFalse(bottom['switches'][0]['activated'])
        self.assertEqual(bottom['switches'][0]['phase'],'call')

    def test_upward_step_limit_is_preserved(self):
        nav = Navigator()
        nav.free = {(0, 0), (1, 0)}
        nav.floors = {(0, 0): 0, (1, 0): 128}
        self.assertEqual(list(nav.neighbors((0, 0))), [])
        self.assertEqual([n for n, _ in nav.neighbors((1, 0))], [(0, 0)])

    def test_locked_door_describes_required_key(self):
        data = map_data(Path(vizdoom.__file__).parent / 'freedoom2.wad', 'MAP02')
        doors = [d for d in data['doors'] if d['sector'] == 37]
        self.assertTrue(doors)
        self.assertEqual({d['key'] for d in doors}, {'yellow'})
        self.assertEqual({d['key'] for d in data['doors'] if d['sector'] == 45}, {None, 'yellow'})


class NavigationMetricsTest(unittest.TestCase):
    @staticmethod
    def row(tick, z=0, enemies=None):
        return dict(tick=tick, episode=0, x=0, y=0, z=z, enemies=enemies or [], ammo=0, buttons=[0]*14)

    def test_lift_height_counts_as_movement(self):
        from check_navigation import analyze
        moving=analyze([self.row(tick,z=tick) for tick in range(180)])
        stationary=analyze([self.row(tick) for tick in range(180)])
        self.assertLess(moving['max_stationary_seconds'],1)
        self.assertGreater(stationary['max_stationary_seconds'],5)

    def test_combat_time_does_not_become_a_navigation_loop(self):
        from check_navigation import analyze
        rows=[self.row(tick,enemies=[{'bearing':0}]) for tick in range(2100)]
        rows += [self.row(tick) for tick in range(2100,2135)]
        result=analyze(rows)
        self.assertLessEqual(result['max_no_new_cell_seconds'],1)
        self.assertLessEqual(result['max_no_new_region_seconds'],1)


class RouteProgressTest(unittest.TestCase):
    def test_return_along_known_route_makes_progress(self):
        from check_navigation import analyze
        rows=[]
        for tick in range(1000):
            row=NavigationMetricsTest.row(tick);row['x']=tick;rows.append(row)
        for offset in range(1400):
            row=NavigationMetricsTest.row(1000+offset);row['x']=999*(1-offset/1399)
            row['execution']=dict(action='exit',target_id=None,status='executing')
            row['navigation']=dict(remaining_distance=row['x']/32);rows.append(row)
        result=analyze(rows)
        self.assertGreater(result['max_no_new_cell_seconds'],25)
        self.assertLess(result['max_no_objective_progress_seconds'],3)

    def test_switching_targets_does_not_hide_circling(self):
        from check_navigation import analyze
        rows=[]
        for tick in range(1400):
            row=NavigationMetricsTest.row(tick);row['x']=16*math.sin(tick/35)
            row['execution']=dict(action='pickup',target_id=(tick//35)%2,status='executing')
            row['navigation']=dict(remaining_distance=10+math.sin(tick/35));rows.append(row)
        self.assertGreater(analyze(rows)['max_no_objective_progress_seconds'],25)


if __name__ == '__main__':
    unittest.main()
