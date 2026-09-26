"""Regression checks for the model/controller authority boundary."""
import copy
import math
import json
from pathlib import Path
import unittest
from executor import Executor
from navigation import Navigator
from policy import request as policy_request
from mission import map_data
import vizdoom

SAMPLE=json.loads((Path(__file__).resolve().parent/'fixtures/authority-state.json').read_text())

class Motor:
    def observe(self,*args):pass
    def steer(self,*args,**kwargs):return [1,0,0,0,0,0,0],['waypoint']
    def state(self,*args):return {}
    def reject(self,*args):pass
    def clear_segment(self,*args):return True

class Exit:
    exit={'center':[0,0]}
    data={'name':'MAP01'}
    def objective(self):return (0,0)
    def activate(self,*args):return None

class AuthorityTest(unittest.TestCase):
    def setup_state(self):
        s=copy.deepcopy(SAMPLE);s['door']=None
        c=Executor(mission=Exit());c.navigator=Motor();c.observe(s,0)
        return c,s

    def test_nearby_pickup_does_not_cut_through_a_wall_or_high_step(self):
        c,s=self.setup_state();item=dict(s['items'][0],distance=1)
        c.known[item['id']]=item
        c.navigator.clear_segment=lambda *args:False
        c.accept(dict(action='pickup',target=item,weapon=None,decision_id=1,command='pickup'),0)
        buttons,refs=c.act(s,0)
        self.assertIn('waypoint',refs)
        self.assertNotIn('approach_selected_item',refs)
        self.assertEqual(s['execution']['target_id'],item['id'])

    def test_nearby_unseen_item_remains_until_engine_confirms_removal(self):
        c,s=self.setup_state();item=dict(s['items'][0],x=s['x']+16,y=s['y'])
        c.known[item['id']]=item;s['items']=[];s['removed_object_ids']=[]
        c.observe(s,1)
        self.assertIn(item['id'],c.known)
        s['removed_object_ids']=[item['id']];c.observe(s,2)
        self.assertNotIn(item['id'],c.known)

    def test_failed_path_is_not_recomputed_every_frame(self):
        nav=Navigator();calls=[]
        nav.nearest=lambda xy:tuple(xy)
        nav.plan=lambda state,tick,goal:calls.append(tick)
        s={'x':0,'y':0,'angle':0}
        for tick in range(100):nav.steer(s,tick,(200,0))
        self.assertEqual(calls,[0,35,70])
        nav.steer(dict(s,x=32),100,(200,0))
        self.assertEqual(calls[-1],100)

    def test_moving_target_inside_one_grid_cell_does_not_trigger_replanning(self):
        nav=Navigator();calls=[]
        nav.nearest=lambda xy:(math.floor(xy[0]/16),math.floor(xy[1]/16))
        nav.plan=lambda state,tick,goal:calls.append(tick)
        for tick in range(100):nav.steer({'x':0,'y':0,'angle':0},tick,(200+tick*.01,0))
        self.assertEqual(calls,[0,35,70])

    def test_unknown_specific_destination_never_falls_back_to_exploration(self):
        nav=Navigator();nav.nearest=lambda xy:(0,0) if xy==(0,0) else None
        nav.plan({'x':0,'y':0},0,(1000,1000))
        self.assertEqual(nav.goal_kind,'unreachable')
        self.assertEqual(nav.path,[])

    def test_unexecutable_pickup_removed_without_selecting_another_action(self):
        c,s=self.setup_state();item=s['items'][0]
        s['target_failures']={str(item['id']):'Unreachable from the current area'}
        packet=policy_request(s,{item['id']:item},Exit())
        self.assertNotIn('collect_'+str(item['id']),packet['commands'])
        self.assertTrue({'exit','explore','wait'}<=set(packet['commands']))
        self.assertEqual(c.act(s,0)[0],[0]*14)

    def test_unreachable_switch_removed_without_selecting_another_action(self):
        c,s=self.setup_state()
        s['switches']=[dict(id=728,activated=False,locked=False,distance=8,kind='lift',phase='call')]
        s['target_failures']={'728':'Unreachable from the current area'}
        packet=policy_request(s,{},Exit())
        self.assertNotIn('switch_728',packet['commands'])
        self.assertIn('explore',packet['commands'])
        self.assertEqual(c.act(s,0)[0],[0]*14)

    def test_normal_door_does_not_reoffer_geometrically_unreachable_targets(self):
        c,s=self.setup_state();item=s['items'][0]
        c.failures[str(item['id'])]='Unreachable from the current area'
        c.command_failures['exit']='No traversable route with the current keys'
        s['opened_doors']=[137]
        c.observe(s,1)
        packet=policy_request(s,c.known,Exit())
        self.assertNotIn('collect_'+str(item['id']),packet['commands'])
        self.assertNotIn('exit',packet['commands'])
        self.assertIn('explore',packet['commands'])
        self.assertEqual(c.act(s,1)[0],[0]*14)

    def test_graph_changes_allow_failed_routes_to_be_retried(self):
        for change in ('key','remote_door','floor','component'):
            with self.subTest(change=change):
                c,s=self.setup_state();item=s['items'][0]
                c.failures[str(item['id'])]='Unreachable from the current area'
                c.command_failures['exit']='No traversable route with the current keys'
                sectors=None
                if change=='key':s['keys']=list(s.get('keys',()))+['red']
                elif change=='remote_door':
                    c.previous_keys=(tuple(s.get('keys',())),(122,))
                    s['closed_remote_doors']=[]
                elif change=='floor':
                    c.navigator.update_floors=lambda _: [159];sectors=[]
                else:
                    c.failure_component={(0,0)};c.navigator.nearest=lambda _: (1,0)
                c.observe(s,1,sectors)
                packet=policy_request(s,c.known,Exit())
                self.assertIn('collect_'+str(item['id']),packet['commands'])
                self.assertIn('exit',packet['commands'])
                self.assertEqual(c.failures,{})
                self.assertEqual(c.command_failures,{})
                self.assertEqual(c.act(s,1)[0],[0]*14)

    def test_strafe_requires_explicit_model_direction(self):
        for movement,expected in ((None,[0,0]),('strafe_left',[1,0]),('strafe_right',[0,1])):
            c,s=self.setup_state();enemy=dict(s['enemies'][0],aim_bearing=0,distance=4)
            s['enemies']=[enemy];s['weapon']=3;s['ammo']=10
            c.accept(dict(action='attack',target=enemy,weapon=3,decision_id=10,command='attack',movement=movement),0)
            buttons,_=c.act(s,0)
            self.assertEqual(buttons[2:4],expected)
            self.assertEqual(buttons[5],1)

    def test_remembered_enemy_is_aimed_at_but_not_fired_on(self):
        c,s=self.setup_state();enemy=dict(s['enemies'][0],visible=False,aim_bearing=20,distance=4)
        s['enemies']=[enemy];s['weapon']=3;s['ammo']=10
        c.accept(dict(action='attack',target=enemy,weapon=3,decision_id=14,command='backpedal',movement='backward'),0)
        buttons,_=c.act(s,0)
        self.assertEqual(buttons[1],1)
        self.assertGreater(buttons[4],0)
        self.assertEqual(buttons[5],0)
        s['enemies']=[dict(enemy,visible=True,aim_bearing=0)]
        self.assertEqual(c.act(s,1)[0][5],1)

    def test_enemy_memory_uses_only_recent_observations(self):
        from agent import Sensors
        from types import SimpleNamespace
        sensors=Sensors()
        enemy=dict(id=5,name='Demon',x=100,y=0,distance=3.125,bearing=0,aim_bearing=0)
        objects={5:SimpleNamespace(name='Demon'),6:SimpleNamespace(name='Demon')}
        sensors.remember_enemies([enemy],objects,0,0,0,0)
        remembered=sensors.remember_enemies([],objects,0,0,0,35)
        self.assertEqual([e['id'] for e in remembered],[5])
        self.assertFalse(remembered[0]['visible'])
        self.assertEqual(sensors.remember_enemies([],objects,0,0,0,71),[])
        sensors.remember_enemies([enemy],objects,0,0,0,100)
        self.assertEqual(sensors.remember_enemies([],{6:objects[6]},0,0,0,101),[])

    def test_lift_ride_holds_only_the_selected_lift_command(self):
        c,s=self.setup_state()
        lift=dict(id=728,name='Lift',activated=False,locked=False,distance=1,phase='ride',approach=[0,0],board=[0,0])
        s['switches']=[lift]
        c.accept(dict(action='use_switch',target=lift,weapon=None,decision_id=11,command='switch_728'),0)
        buttons,refs=c.act(s,0)
        self.assertEqual(buttons,[0]*14)
        self.assertIn('ride_selected_lift',refs)
        c.accept(dict(action='exit',target=None,weapon=None,decision_id=12,command='exit'),1)
        self.assertEqual(c.act(s,1)[0],[1]+[0]*13)

    def test_continuation_keeps_only_the_goal_explicitly_selected_by_model(self):
        from decision_questions import factorize,with_commitment
        from policy import decode
        c,s=self.setup_state();first=s['enemies'][0];second=dict(first,id=first['id']+100)
        s['enemies']=[first,second]
        s['execution']=dict(action='attack',target_id=first['id'],movement='strafe_left',status='executing')
        packet=with_commitment(factorize(policy_request(s,{},Exit())))
        result={'answers':{'command':{'choice':'continue'},'enemy':{'choice':str(second['id'])},
                           'movement':{'choice':'continue'},'weapon':{'choice':'pistol'}}}
        directive=decode(result,packet,20)
        self.assertEqual(directive['target']['id'],first['id'])
        self.assertEqual(directive['movement'],'strafe_left')
        result['answers']['command']['choice']='attack'
        self.assertEqual(decode(result,packet,21)['target']['id'],second['id'])
        result['answers']['command']['choice']='wait'
        directive=decode(result,packet,22)
        self.assertEqual(directive['action'],'wait')
        self.assertIsNone(directive['target'])
        self.assertNotIn('movement',directive)
        s['execution']['status']='blocked'
        blocked=with_commitment(factorize(policy_request(s,{},Exit())))
        self.assertNotIn('continue',blocked['questions']['command']['criteria'])

    def test_explicit_action_uses_fresh_target_and_preserves_movement_choice(self):
        from decision_questions import factorize,with_commitment,without_action_continuation,dependencies
        from policy import decode
        _,s=self.setup_state();first=s['enemies'][0];second=dict(first,id=first['id']+100)
        s['enemies']=[first,second]
        s['execution']=dict(action='attack',target_id=first['id'],movement='strafe_left',status='executing')
        packet=with_commitment(factorize(policy_request(s,{},Exit())))
        before=copy.deepcopy(packet)
        without_action_continuation(packet)
        self.assertEqual(packet['state'],before['state'])
        self.assertEqual(packet['targets'],before['targets'])
        self.assertEqual(set(packet['questions']['command']['criteria']),set(before['questions']['command']['criteria'])-{'continue'})
        self.assertNotIn('continue',packet['commands'])
        self.assertEqual(set(dependencies(packet)['attack']),{'enemy','movement'})
        answer={'answers':{'command':{'choice':'attack'},'enemy':{'choice':str(second['id'])},
                           'movement':{'choice':'continue'},'weapon':{'choice':'pistol'}}}
        directive=decode(answer,packet,20)
        self.assertEqual(directive['target']['id'],second['id'])
        self.assertEqual(directive['movement'],'strafe_left')
        answer['answers'].pop('enemy')
        with self.assertRaises(KeyError):decode(answer,packet,21)

    def test_super_shotgun_uses_slot_three_and_requires_two_shells(self):
        c,s=self.setup_state();enemy=dict(s['enemies'][0],aim_bearing=0,distance=2)
        s['enemies']=[enemy];s['inventory']['8']={'owned':1,'ammo':10};s.update(weapon=3,ammo=10)
        c.accept(dict(action='attack',target=enemy,weapon=8,decision_id=1,command='attack'),0)
        buttons,_=c.act(s,0)
        self.assertEqual(buttons[9],1)
        self.assertEqual(buttons[5],0)
        s.update(weapon=8,ammo=1)
        self.assertEqual(c.act(s,1)[0][5],0)
        s['ammo']=2
        self.assertEqual(c.act(s,2)[0][5],1)
        from items import utility
        upgrade=dict(s['items'][0],name='SuperShotgun',category='Weapon')
        self.assertEqual(utility(upgrade,s),0)
        s['inventory']['8']['owned']=0
        self.assertEqual(utility(upgrade,s),100)

    def test_reachable_item_observation_does_not_change_combat_or_select_a_target(self):
        from types import SimpleNamespace
        c,s=self.setup_state();item=dict(s['items'][0],x=8,y=8)
        c.known={item['id']:item};before=copy.deepcopy(s['walls'])
        c.navigator=SimpleNamespace(nearest=lambda xy:xy,reachable=lambda xy:{(8,8)})
        directive=c.directive
        c.annotate_reachable_items(s)
        self.assertTrue(c.known[item['id']]['reachable'])
        self.assertEqual(s['walls'],before)
        self.assertNotIn('motion_clearance',s)
        self.assertIs(c.directive,directive)

    def test_reachability_facts_are_refreshed_after_a_one_way_drop(self):
        from types import SimpleNamespace
        c,s=self.setup_state();item=dict(s['items'][0],x=0,y=0)
        c.known={item['id']:item}
        c.navigator=SimpleNamespace(nearest=lambda xy:xy,
            reachable=lambda xy:{(0,0),(1,0)} if xy==(0,0) else {(1,0)},
            movement_clearance=lambda state:{'back':0.,'left':3.,'right':4.})
        s.update(x=0,y=0);c.annotate_physical_facts(s)
        self.assertTrue(c.known[item['id']]['reachable'])
        s['x']=1;c.annotate_physical_facts(s)
        self.assertFalse(c.known[item['id']]['reachable'])
        self.assertIn('collect_'+str(item['id']),policy_request(s,c.known,Exit())['commands'])

    def test_body_clearance_measures_the_wall_behind_the_player(self):
        from shapely.geometry import box
        nav=Navigator();nav.walk=box(0,0,320,320)
        nav.free={(x,y) for x in range(20) for y in range(20)}
        nav.floors={cell:0 for cell in nav.free}
        measured=nav.movement_clearance(dict(x=40,y=160,angle=0),limit=160)
        self.assertEqual(measured['back'],1.25)
        self.assertEqual(measured['ahead'],5.)
        self.assertEqual(measured['left'],5.)
        self.assertEqual(measured['right'],5.)
        nav.floors.update({cell:64 for cell in nav.free if cell[0]>=5})
        self.assertLess(nav.movement_clearance(dict(x=40,y=160,angle=0),limit=160)['ahead'],1.5)

    def test_pickup_combat_is_an_independent_explicit_model_choice(self):
        from decision_questions import factorize,with_commitment,with_pickup_combat,dependencies
        from policy import decode
        c,s=self.setup_state();item=s['items'][0];enemy=s['enemies'][0]
        packet=with_pickup_combat(with_commitment(factorize(policy_request(s,{item['id']:item},Exit()))))
        self.assertEqual(set(dependencies(packet)['pickup']),{'item','combat'})
        answer={'answers':{'command':{'choice':'pickup'},'item':{'choice':str(item['id'])},
                           'combat':{'choice':str(enemy['id'])},'weapon':{'choice':'pistol'}}}
        command=decode(answer,packet,1)
        self.assertEqual(command['target'],item)
        self.assertEqual(command['combat_target'],enemy)
        answer['answers']['combat']['choice']='hold'
        self.assertIsNone(decode(answer,packet,2)['combat_target'])
        s['enemies']=[dict(enemy,visible=False)]
        packet=with_pickup_combat(with_commitment(factorize(policy_request(s,{item['id']:item},Exit()))))
        self.assertEqual(list(packet['questions']['combat']['criteria']),['hold'])

    def test_pickup_can_follow_route_while_firing_only_at_selected_enemy(self):
        c,s=self.setup_state();s.update(angle=0,weapon=3,ammo=10)
        item=dict(s['items'][0],x=s['x'],y=s['y']+100,distance=100/32)
        c.known={item['id']:item};c.navigator.steering_target=(item['x'],item['y'])
        enemy=dict(s['enemies'][0],aim_bearing=0,bearing=0,distance=4,visible=True)
        s['enemies']=[enemy]
        command=dict(action='pickup',target=item,combat_target=enemy,weapon=3,
                     decision_id=1,command='pickup',expires_tick=70)
        c.accept(command,0);buttons,refs=c.act(s,0)
        self.assertEqual(buttons[:6],[0,0,1,0,0,1])
        self.assertEqual(s['execution']['target_id'],item['id'])
        self.assertEqual(s['execution']['combat_target_id'],enemy['id'])
        self.assertIn('route_while_aiming_selected_enemy',refs)
        s['enemies']=[dict(enemy,id=enemy['id']+1)]
        self.assertEqual(c.act(s,1)[0][5],0)
        s['enemies']=[enemy];c.accept(dict(command,combat_target=None),2)
        self.assertEqual(c.act(s,2)[0][:6],[1,0,0,0,0,0])
        c.accept(command,3)
        self.assertEqual(c.act(s,71)[0],[0]*14)

    def test_pickup_combat_keeps_height_adjusted_contact_point(self):
        c,s=self.setup_state();s.update(angle=0,weapon=3,ammo=10)
        item=dict(s['items'][0],x=s['x']+16,y=s['y'],z=0,distance=.5)
        c.known={item['id']:item}
        contact=(s['x'],s['y']+16)
        c.navigator.pickup_point=lambda value:contact
        c.navigator.clear_segment=lambda origin,target:True
        enemy=dict(s['enemies'][0],aim_bearing=0,bearing=0,distance=4,visible=True)
        s['enemies']=[enemy]
        c.accept(dict(action='pickup',target=item,combat_target=enemy,weapon=3,
                      decision_id=1,command='pickup',expires_tick=70),0)
        buttons,refs=c.act(s,0)
        self.assertIn('approach_selected_item',refs)
        self.assertEqual(buttons[:4],[0,0,1,0])
        self.assertEqual(s['execution']['target_id'],item['id'])

    def test_continued_combat_can_request_a_new_model_selected_enemy(self):
        from decision_questions import factorize,with_commitment,refresh_attack_target,dependencies
        from policy import decode
        c,s=self.setup_state();first=s['enemies'][0];second=dict(first,id=first['id']+100,distance=first['distance']+10)
        s['enemies']=[first,second]
        s['execution']=dict(action='attack',target_id=first['id'],movement='strafe_left',status='executing')
        packet=refresh_attack_target(with_commitment(factorize(policy_request(s,{},Exit()))))
        self.assertEqual(set(dependencies(packet)['continue']),{'enemy','movement'})
        self.assertIn(f"{first['distance']:.1f}m",packet['questions']['command']['criteria']['continue'])
        result={'answers':{'command':{'choice':'continue'},'enemy':{'choice':str(second['id'])},
                           'movement':{'choice':'continue'},'weapon':{'choice':'pistol'}}}
        directive=decode(result,packet,20)
        self.assertEqual(directive['target'],second)
        self.assertEqual(directive['movement'],'strafe_left')
        self.assertEqual(directive['action'],'attack')
        result['answers']['command']['choice']='wait'
        self.assertIsNone(decode(result,packet,21)['target'])

    def test_conditional_requests_ask_only_for_selected_action_parameters(self):
        from agent import LayaClient
        from decision_questions import factorize,with_commitment,dependencies
        c,s=self.setup_state();enemy=s['enemies'][0]
        s['execution']=dict(action='attack',target_id=enemy['id'],movement='strafe_left',status='executing')
        packet=with_commitment(factorize(policy_request(s,{i['id']:i for i in s['items']},Exit())))
        class Stub(LayaClient):
            def __init__(self,choice,change_weights=False):self.choice=choice;self.calls=[];self.change_weights=change_weights
            def predict(self,text,questions=None,dependencies=None):
                if dependencies is not None:return self.predict_conditional(text,questions,dependencies)
                self.calls.append(set(questions));answers={}
                for key,q in questions.items():
                    value=self.choice if key=='command' else next(iter(q['criteria']))
                    answers[key]=dict(choice=value,probabilities={k:float(k==value) for k in q['criteria']})
                root=answers.get('command',{})
                return dict(choice=root.get('choice'),probabilities=root.get('probabilities',{}),answers=answers,
                            raw_probabilities={k:v['probabilities'] for k,v in answers.items()},tokens=7*len(questions),cost_usd=.01,
                            latency_ms=0,server_latency_ms=0,routing={'weights_sha256':'changed' if self.change_weights and len(self.calls)>1 else 'same'})
        for choice,extra in [('continue',{'movement'}),('attack',{'enemy','movement'}),('pickup',{'item'}),('wait',set())]:
            with self.subTest(choice=choice):
                client=Stub(choice);result=client.predict(packet['state'],packet['questions'],dependencies(packet))
                self.assertEqual(client.calls,[{'command','weapon'}]+([extra] if extra else []))
                self.assertEqual(set(result['answers']),{'command','weapon'}|extra)
                self.assertEqual(result['tokens'],7*(2+len(extra)))
                self.assertAlmostEqual(result['cost_usd'],.01*len(client.calls))
        with self.assertRaisesRegex(ValueError,'Checkpoint changed'):
            Stub('attack',True).predict(packet['state'],packet['questions'],dependencies(packet))

    def test_factorized_answers_choose_action_target_weapon_and_movement(self):
        from decision_questions import factorize
        from policy import decode
        c,s=self.setup_state()
        first=s['enemies'][0];second=dict(first,id=first['id']+100)
        s['enemies']=[first,second]
        packet=factorize(policy_request(s,{},Exit()))
        result={'answers':{'command':{'choice':'attack'},'enemy':{'choice':str(second['id'])},
                           'movement':{'choice':'backward'},'weapon':{'choice':'pistol'}}}
        directive=decode(result,packet,15)
        self.assertEqual(directive['target'],second)
        self.assertEqual(directive['movement'],'backward')
        self.assertEqual(directive['weapon'],2)
        self.assertEqual(list(packet['questions']['command']['criteria']).count('attack'),1)
        result['answers']['command']['choice']='wait'
        directive=decode(result,packet,16)
        self.assertIsNone(directive['target'])
        self.assertNotIn('movement',directive)
        c.accept(directive,0)
        self.assertEqual(c.act(s,0)[0][:7],[0]*7)

    def test_observed_key_replaces_its_map_marker_without_two_pickup_targets(self):
        from types import SimpleNamespace
        marker=dict(id='key_14',name='RedCard',color='red',category='Key',x=100,y=100,source='wad')
        mission=SimpleNamespace(data=dict(key_markers=[marker]),exit=None)
        c=Executor(mission=mission);c.navigator=Motor();c.known[marker['id']]=dict(marker)
        s=copy.deepcopy(SAMPLE);s['keys']=[];s['items']=[dict(marker,id=5,source='observation')]
        c.observe(s,0)
        self.assertEqual(set(c.known),{5})
        self.assertEqual(c.known[5]['name'],'RedCard')

    def test_map01_wall_208_is_not_a_manual_door(self):
        data=map_data(Path(vizdoom.__file__).parent/'freedoom2.wad','MAP01')
        self.assertEqual(set(data['door_sectors']),{27,56,121,161})
        self.assertNotIn(208,data['door_sectors'])

    def test_weapon_animation_never_fires_the_previous_weapon(self):
        c,s=self.setup_state();enemy=dict(s['enemies'][0],aim_bearing=0,distance=1)
        s['enemies']=[enemy];s['weapon']=2;s['ammo']=20
        c.accept({'action':'attack','target':enemy,'weapon':1,'decision_id':8,'command':'shoot'},0)
        self.assertEqual(c.act(s,0)[0][5],0)
        self.assertEqual(c.act(s,1)[0][5],0)

    def test_idle_has_no_implicit_combat_pickup_or_weapon_switch(self):
        for command in (None,{'action':'wait','target':None,'weapon':None,'decision_id':1,'command':'wait'}):
            c,s=self.setup_state()
            if command:c.accept(command,0)
            buttons,_=c.act(s,0)
            self.assertEqual(buttons,[0]*14)
            self.assertIsNone(s['resource']['target'])

    def test_exit_with_monster_and_items_only_moves(self):
        c,s=self.setup_state();c.accept({'action':'exit','target':None,'weapon':None,'decision_id':2,'command':'exit'},0)
        buttons,_=c.act(s,0)
        self.assertEqual(buttons,[1]+[0]*13)
        self.assertIsNone(s['resource']['target'])

    def test_attack_exact_target_and_no_retarget_after_disappearance(self):
        c,s=self.setup_state();enemy=dict(s['enemies'][0],aim_bearing=0,distance=4)
        s['enemies'][0]=enemy;s['weapon']=2;s['ammo']=20
        c.accept({'action':'attack','target':enemy,'weapon':None,'decision_id':3,'command':'shoot'},0)
        self.assertEqual(c.act(s,0)[0][5],1)
        s['enemies']=[dict(enemy,id=enemy['id']+999)]
        self.assertEqual(c.act(s,1)[0],[0]*14)
        self.assertEqual(s['execution']['status'],'unavailable')

    def test_far_melee_approaches_selected_enemy_without_punching_air(self):
        c,s=self.setup_state();enemy=dict(s['enemies'][0],aim_bearing=0,distance=14)
        s['enemies']=[enemy];s['weapon']=1
        c.accept({'action':'attack','target':enemy,'weapon':1,'decision_id':7,'command':'shoot'},0)
        buttons,refs=c.act(s,0)
        self.assertEqual(buttons[0],1)
        self.assertEqual(buttons[5],0)
        self.assertIn('approach_selected_enemy',refs)
        self.assertEqual(s['execution']['target_id'],enemy['id'])

    def test_ranged_attack_does_not_turn_away_to_approach_a_visible_enemy(self):
        c,s=self.setup_state();enemy=dict(s['enemies'][0],aim_bearing=0,distance=20)
        s['enemies']=[enemy];s['weapon']=3;s['ammo']=10
        c.accept({'action':'attack','target':enemy,'weapon':3,'decision_id':9,'command':'shoot'},0)
        buttons,_=c.act(s,0)
        self.assertEqual(buttons[:5],[0]*5)
        self.assertEqual(buttons[5],1)

    def test_changing_enemy_does_not_reset_collision_detection(self):
        c,s=self.setup_state();first=s['enemies'][0];second=dict(first,id=first['id']+100)
        s['enemies']=[first,second];s['walls']={'left':5.,'right':1.,'ahead':3.}
        for tick in range(36):
            enemy=first if (tick//10)%2 else second
            c.accept(dict(action='attack',target=enemy,weapon=3,decision_id=tick+1,
                          command='attack',movement='backward'),tick)
            buttons,refs=c.act(s,tick)
        self.assertIn('recover_same_goal',refs)
        self.assertEqual(s['execution']['target_id'],enemy['id'])
        self.assertEqual(buttons[2:4],[1.,0.])
        c.accept(dict(action='attack',target=first,weapon=3,decision_id=37,
                      command='attack',movement='backward'),36)
        self.assertIn('recover_same_goal',c.act(s,36)[1])

    def test_attack_collision_recovery_keeps_aim_and_fire_at_selected_enemy(self):
        c,s=self.setup_state();enemy=dict(s['enemies'][0],aim_bearing=0,distance=4)
        s['enemies']=[enemy];s['weapon']=3;s['ammo']=10
        c.accept(dict(action='attack',target=enemy,weapon=3,decision_id=13,command='backpedal',movement='backward'),0)
        s['walls']={'left':5,'right':1,'ahead':8}
        c.act(s,0)
        buttons,refs=c.act(s,35)
        self.assertEqual(buttons[:4],[0,0,1,0])
        self.assertIn('recover_same_goal',refs)
        self.assertEqual(buttons[4],0)
        self.assertEqual(buttons[5],1)
        self.assertEqual(s['execution']['target_id'],enemy['id'])

        resumed,refs=c.act(s,53)
        self.assertNotIn('recover_same_goal',refs)
        self.assertEqual(resumed[:4],[0,1,0,0])
        self.assertEqual(resumed[5],1)

    def test_door_requires_its_own_command(self):
        c,s=self.setup_state();s['door']={'id':42,'x':s['x']+30,'y':s['y'],'distance':1,'bearing':0}
        c.accept({'action':'exit','target':None,'weapon':None,'decision_id':4,'command':'exit'},0)
        self.assertEqual(c.act(s,0)[0],[0]*14)
        self.assertEqual(s['execution']['status'],'blocked')

    def test_weapon_selection_is_explicit_and_expired_command_is_idle(self):
        c,s=self.setup_state();s['weapon']=2
        c.accept({'action':'wait','target':None,'weapon':1,'decision_id':5,'command':'wait','expires_tick':5},0)
        self.assertEqual(c.act(s,0)[0][7],1)
        self.assertEqual(c.act(s,6)[0],[0]*14)

    def test_pickup_is_exact_target_even_with_visible_enemies(self):
        c,s=self.setup_state();item=s['items'][0]
        c.accept({'action':'pickup','target':item,'weapon':None,'decision_id':6,'command':'collect'},0)
        buttons,_=c.act(s,0)
        self.assertEqual(s['resource']['target']['id'],item['id'])
        self.assertEqual(buttons[5:], [0]*9)

if __name__=='__main__':unittest.main()
