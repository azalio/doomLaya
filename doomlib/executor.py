"""Execute explicit model commands; no combat, item or weapon preference policy."""
import math
from doomlib.navigation import Navigator
from doomlib.decision_questions import NAVIGATION_ACTIONS
from doomlib.combat import target_bearing,WEAPON_SLOTS,AMMO_COST


class Executor:
    def __init__(self,sectors=None,mission=None,map_weapons=False,mechanism_facts=False,attack_turn_rate=9):
        if attack_turn_rate not in (9,18,36):raise ValueError('Attack turn rate must be 9, 18 or 36 degrees per tick')
        self.attack_turn_rate=attack_turn_rate
        doors=list(mission.data.get('doors',())) if mission else []
        if mission:doors.extend({'sector':i,'key':None} for switch in mission.data.get('switches',()) for i in switch['sectors'])
        self.navigator=Navigator(sectors,doors,mission.data.get('teleports',()) if mission else ())
        self.mission=mission
        if mechanism_facts and mission:mission.annotate_lift_routes(self.navigator)
        self.map_weapons=map_weapons
        self.directive=None
        self.known={}
        self.previous=None
        self.execution={'status':'waiting','detail':'No model decision yet'}
        self.anchor=None
        self.anchor_tick=0
        self.failures={}
        self.failure_origin=None
        self.command_failures={}
        self.failure_component=None
        self.previous_keys=None
        self.escape_start=-1000
        self.escape_side=1
        self.last_selection=-1000
        self.reachable_cache=None
        self.look_goal_angle=None

    def observe(self,s,tick,sectors=None):
        s['geometry_changes']=self.navigator.update_geometry(sectors) if sectors is not None else []
        s['floor_changes']=self.navigator.update_floors(sectors) if sectors is not None else []
        if s['floor_changes'] or s['geometry_changes']:self.reachable_cache=None
        self.navigator.observe(s,tick)
        keys=(tuple(s.get('keys',())),tuple(s.get('closed_remote_doors',())))
        # Normal doors are already traversable in the graph; opening one cannot repair a failed path.
        if (self.failure_component is not None and self.navigator.nearest((s['x'],s['y'])) not in self.failure_component) or s.get('floor_changes') or s.get('geometry_changes') or keys!=self.previous_keys:
            self.failures.clear()
            self.command_failures.clear()
            self.failure_origin=None
            self.failure_component=None
        self.previous_keys=keys
        # Keep an observed, model-selected door available while turning toward its approach.
        selected=(self.directive or {}).get('target')
        if (self.directive or {}).get('action')=='open_door' and selected and selected['id'] in s.get('closed_doors',()):
            if not s.get('door') or s['door']['id']!=selected['id']:
                remembered=dict(selected)
                remembered['distance']=math.dist((s['x'],s['y']),(selected['x'],selected['y']))/32
                remembered['bearing']=target_bearing(remembered,s)
                s['door']=remembered
        visible={i['id']:i for i in s['items']}
        self.known.update({k:dict(v) for k,v in visible.items()})
        if self.mission:
            for marker in self.mission.data.get('key_markers',()):
                if marker['color'] in s.get('keys',()):
                    for key,item in list(self.known.items()):
                        if item['category']=='Key' and item['name'].lower().startswith(marker['color']):self.known.pop(key,None)
                elif any(key!=marker['id'] and item['category']=='Key' and item['name']==marker['name'] and math.dist((item['x'],item['y']),(marker['x'],marker['y']))<1 for key,item in self.known.items()):
                    self.known.pop(marker['id'],None)
                elif marker['id'] not in self.known:
                    self.known[marker['id']]=dict(marker)
        if self.mission and self.map_weapons:
            for marker in self.mission.data.get('weapon_markers',()):
                collected=any(i['name']==marker['name'] and math.dist((i['x'],i['y']),(marker['x'],marker['y']))<1 for i in s.get('collected_weapons',()))
                observed=any(key!=marker['id'] and item['name']==marker['name'] and math.dist((item['x'],item['y']),(marker['x'],marker['y']))<1 for key,item in self.known.items())
                if collected or observed:self.known.pop(marker['id'],None)
                elif marker['id'] not in self.known:self.known[marker['id']]=dict(marker)
        for key,item in list(self.known.items()):
            item['distance']=math.hypot(item['x']-s['x'],item['y']-s['y'])/32
            if key in s.get('removed_object_ids',()):del self.known[key]
        gains={}
        if self.previous:
            for field in ('hp','armor'):
                diff=s[field]-self.previous[field]
                if diff>0:gains[field]=diff
            for slot in ('2','3','5','6'):
                diff=s['inventory'][slot]['ammo']-self.previous['inventory'][slot]['ammo']
                if diff>0:gains['ammo_'+slot]=diff
            for slot,entry in s['inventory'].items():
                diff=entry['owned']-self.previous['inventory'][slot]['owned']
                if diff>0:gains['weapon_'+slot]=diff
        self.previous={'hp':s['hp'],'armor':s['armor'],'inventory':s['inventory']}
        s['resource']={'gains':gains,'known_items':len(self.known),'target':None}
        s['execution']=dict(self.execution)
        s['target_failures']=dict(self.failures)
        s['command_failures']=dict(self.command_failures)

    def annotate_reachable_items(self,s):
        here=self.navigator.nearest((s['x'],s['y']))
        signature=(here,tuple(s.get('keys',())),tuple(s.get('closed_remote_doors',())))
        cached=self.reachable_cache
        if cached is None or cached[0]!=signature or here not in cached[1]:
            cached=(signature,self.navigator.reachable((s['x'],s['y'])))
            self.reachable_cache=cached
        for item in self.known.values():
            point=self.navigator.pickup_point(item) if 'z' in item else (item['x'],item['y'])
            item['reachable']=self.navigator.nearest(point) in cached[1]
        s['reachable_items']={str(i['id']):i['reachable'] for i in self.known.values()}

    def annotate_physical_facts(self,s):
        self.annotate_reachable_items(s)
        s['motion_clearance']=self.navigator.movement_clearance(s)

    def accept(self,directive,tick):
        from doomlib.enemy_sequences import validate_sequence
        validate_sequence(directive)
        self.sequence_index=0
        old=self.directive or {}
        changed=(old.get('action'),(old.get('target') or {}).get('id')) != (directive['action'],(directive.get('target') or {}).get('id'))
        if changed and not (old.get('action')==directive['action']=='attack'):
            self.anchor=None
            self.anchor_tick=tick
            self.escape_start=-1000
        if old.get('action')!=directive['action'] or tick>old.get('expires_tick',float('inf')):
            self.look_goal_angle=None
        self.directive=directive

    def act(self,s,tick):
        d=self.directive or {'action':'wait','target':None,'weapon':None,'decision_id':None,'command':'wait'}
        if tick>d.get('expires_tick',float('inf')):
            d={'action':'wait','target':None,'weapon':None,'decision_id':None,'command':'expired'}
        from doomlib.enemy_sequences import advance_sequence
        kind=d['action'];target=d.get('target')
        if kind=='attack':target,self.sequence_index=advance_sequence(d,s['enemies'],getattr(self,'sequence_index',0))
        a=[0.]*14
        refs=[]
        status='executing';detail=kind
        current=None
        if kind=='look_back':
            if self.look_goal_angle is None:self.look_goal_angle=(s['angle']-180)%360
            remaining=(s['angle']-self.look_goal_angle)%360
            if remaining<.2 or remaining>180.2:
                status,detail='arrived','Turned clockwise 180 degrees'
            else:
                a[4]=min(9,remaining)
                refs=['turn_as_selected_by_model']
        elif kind=='attack':
            current=next((e for e in s['enemies'] if e['id']==target['id']),None) if target else None
            if current:
                b=current.get('aim_bearing',current['bearing'])
                a[4]=max(-self.attack_turn_rate,min(self.attack_turn_rate,b))
                melee=AMMO_COST[s['weapon']]==0
                usable=s['ammo']>=AMMO_COST[s['weapon']]
                a[5]=float(current.get('visible',True) and abs(b)<5 and usable and (not melee or current['distance']<=1.5))
                refs=['aim_selected_enemy']
                if melee and current['distance']>1.4 and not d.get('movement'):
                    move,motor_refs=self.navigator.steer(s,tick,(current['x'],current['y']))
                    if 'navigation_exhausted' not in motor_refs:
                        a[:5]=move[:5]
                        a[5]=float(a[5] and abs(move[4]-b)<5)
                        refs+=motor_refs+['approach_selected_enemy']
                    elif melee:
                        status,detail='blocked','Selected melee weapon is out of range and there is no path to the enemy'
            else:status,detail='unavailable','Selected enemy is no longer visible; select a new command'
            # Movement has its own explicit model choice and directive expiry.
            # Losing the target suppresses aim/fire, not the requested movement.
            if d.get('movement')=='strafe_left':a[2]=1
            elif d.get('movement')=='strafe_right':a[3]=1
            elif d.get('movement')=='backward':a[1]=1
        elif kind in ('pickup','open_door','use_switch','exit','explore'):
            objective=None;available=True
            if kind=='pickup':
                current=self.known.get(target['id']) if target else None
                if current:
                    objective=self.navigator.pickup_point(current) if 'z' in current else (current['x'],current['y'])
                    s['resource']['target']=dict(current)
                else:available=False
            elif kind=='open_door':
                current=s['door'] if s['door'] and target and s['door']['id']==target['id'] else None
                if current:objective=current.get('approach',(current['x'],current['y']))
                else:available=False
            elif kind=='use_switch':
                current=next((v for v in s.get('switches',()) if target and v['id']==target['id']),None)
                available=bool(current and not current['activated'] and not current['locked'])
                if available:objective=current['board'] if current.get('phase')=='board' else current['approach']
            elif kind=='exit':
                available=bool(self.mission and self.mission.exit)
                if available:objective=self.mission.objective()
            if not available:status,detail='unavailable','Selected target is no longer observable or present'
            else:
                a[:7],refs=self.navigator.steer(s,tick,objective)
                if kind=='pickup' and current['distance']<2 and self.navigator.clear_segment((s['x'],s['y']),objective):
                    b=target_bearing(dict(x=objective[0],y=objective[1]),s)
                    a[:7]=[float(abs(b)<20),0,0,0,max(-6,min(6,b)),0,0]
                    refs=['approach_selected_item']
                if kind=='open_door' and current['distance']<2.8 and ('approach' not in current or math.dist((s['x'],s['y']),current['approach'])<32):
                    # Align with the selected doorway before using it from a corner.
                    center=current.get('center',(current['x'],current['y']))
                    b=target_bearing(dict(x=center[0],y=center[1]),s)
                    a[:7]=[float(abs(b)<20 and current['distance']>1.8),0,0,0,max(-6,min(6,b)),0,float(abs(b)<12 and tick%12==0)]
                    refs=['open_selected_door']
                if kind=='use_switch' and current.get('phase')=='ride':
                    a[:7]=[0.]*7;refs=['ride_selected_lift']
                elif kind=='use_switch' and current.get('phase')=='board' and math.dist((s['x'],s['y']),current['board'])<96:
                    point=dict(x=current['board'][0],y=current['board'][1]);b=target_bearing(point,s)
                    a[:7]=[float(abs(b)<20),0,0,0,max(-6,min(6,b)),0,0];refs=['board_selected_lift']
                elif kind=='use_switch' and current['distance']<2:
                    b=target_bearing(current,s)
                    a[:7]=[float(abs(b)<20 and current['distance']>1.6),0,0,0,max(-6,min(6,b)),0,float(abs(b)<10 and tick%12==0)]
                    refs=['use_selected_switch']
                if kind=='exit':
                    activation=self.mission.activate(s,tick)
                    if activation is not None:a[:7],refs=activation,['activate_selected_exit']
                door=s['door']
                if kind!='open_door' and 'activate_selected_exit' not in refs and door and door['distance']<2.7 and abs(door['bearing'])<25 and a[0]:
                    a[:7]=[0.]*7
                    status,detail='blocked','A closed door blocks movement; choose open_door to open it'
                elif kind=='open_door' and current.get('locked'):
                    a[:7]=[0.]*7
                    status,detail='blocked','Door requires the '+current['required_key']+' key'
                elif 'navigation_exhausted' in refs:
                    status,detail='blocked','No navigable path to the selected target'
                    if self.failure_component is None:self.failure_component=self.navigator.reachable((s['x'],s['y']))
                    if kind=='exit':
                        self.command_failures['exit']='No traversable route with the current keys'
                        if self.failure_origin is None:self.failure_origin=(s['x'],s['y'])
                    if target:
                        self.failures[str(target['id'])]='Unreachable from the current area'
                        if self.failure_origin is None:self.failure_origin=(s['x'],s['y'])
                elif target:self.failures.pop(str(target['id']),None)
        elif kind=='retreat':a[1]=1
        else:status,detail='waiting','Model chose wait' if d['decision_id'] is not None else 'No accepted model command'
        combat_target=d.get('combat_target') if kind in NAVIGATION_ACTIONS else None
        combat_enemy=next((e for e in s['enemies'] if combat_target and e['id']==combat_target['id']),None)
        if combat_enemy:
            b=combat_enemy.get('aim_bearing',combat_enemy['bearing'])
            turn=max(-9,min(9,b))
            point=None
            if status=='executing':
                if 'approach_selected_item' in refs:point=objective
                elif 'waypoint' in refs:point=self.navigator.steering_target
            activation=any(ref in refs for ref in ('open_selected_door','use_selected_switch','board_selected_lift','activate_selected_exit'))
            if activation:
                combat_enemy=None
            elif point is not None:
                # Follow the selected world-space route while facing the selected enemy.
                move_bearing=target_bearing(dict(x=point[0],y=point[1]),s)-turn
                direction=round(move_bearing/45)%8
                a[:4]=[(1,0,0,0),(1,0,0,1),(0,0,0,1),(0,1,0,1),
                       (0,1,0,0),(0,1,1,0),(0,0,1,0),(1,0,1,0)][direction]
                refs.append('route_while_aiming_selected_enemy')
            elif any(a[:4]):
                # Specialized route activations keep their original view direction.
                combat_enemy=None
            if combat_enemy:
                a[4]=turn
                melee=AMMO_COST[s['weapon']]==0
                usable=s['ammo']>=AMMO_COST[s['weapon']]
                a[5]=float(combat_enemy.get('visible',True) and abs(b)<5 and usable and (not melee or combat_enemy['distance']<=1.5))
                refs.append('aim_secondary_model_enemy')
        fighting=kind=='attack' or combat_enemy is not None
        # Collision recovery changes motor commands, never the requested objective.
        xy=(s['x'],s['y'])
        moving=bool(any(a[:4]))
        if not moving or self.anchor is None or math.dist(xy,self.anchor)>24:
            self.anchor,self.anchor_tick=xy,tick
        if moving and tick-self.anchor_tick>=35 and tick-self.escape_start>=70:
            self.escape_start=tick
            self.escape_side=-1 if s['walls']['left']>s['walls']['right'] else 1
            self.navigator.reject(tick)
            refs.append('stuck')
        elapsed=tick-self.escape_start
        recovery_ticks=18 if fighting else 42
        if kind in ('attack','exit','explore','pickup','open_door','use_switch','retreat') and status=='executing' and elapsed<recovery_ticks:
            if fighting:
                # Step sideways out of a collision; backing into the same wall cannot release it.
                a[:4]=[0,0,float(self.escape_side<0),float(self.escape_side>0)]
            else:
                a[:5]=[0,float(elapsed<18),0,0,self.escape_side*7 if elapsed>=18 else 0]
                a[5]=0
            a[6]=0
            refs.append('recover_same_goal')
        selection=d.get('weapon')
        if selection and s['weapon']!=selection:a[5]=0
        if selection and s['inventory'][str(selection)]['owned'] and s['weapon']!=selection and tick-self.last_selection>=12:
            a[6+WEAPON_SLOTS[selection]]=1
            a[5]=0
            self.last_selection=tick
            refs.append('select_model_weapon')
        if self.mission and kind=='use_switch' and target and a[6] and target.get('kind')=='door':
            self.mission.note_switch_use(target['id'],s.get('engine_tic',tick))
        if target:detail+=f" ({target.get('name',kind)} #{target['id']})"
        self.execution={'status':status,'detail':detail,'decision_id':d['decision_id'],'command':d['command'],'action':kind,
                        'target_id':target['id'] if target else None,'weapon':selection,'movement':d.get('movement'),
                        'combat_target_id':combat_target['id'] if combat_target else None}
        if 'target_sequence' in d:self.execution['sequence_index']=self.sequence_index
        s['execution']=dict(self.execution)
        aimed_target=target if kind=='attack' else combat_target
        s['combat']={'mode':kind+('+fire' if combat_target else ''),'target_id':aimed_target['id'] if aimed_target else None,
                     'target_name':aimed_target.get('name') if aimed_target else None,
                     'target_visible':bool(current and current.get('visible',True)) if kind=='attack' else bool(combat_enemy and combat_enemy.get('visible',True)),'preferred_weapon':selection,'selection':next((i for i in range(1,8) if a[6+i]),0)}
        s['mission']={'map':self.mission.data['name'],'exit':self.mission.exit} if self.mission else None
        s['navigation']=self.navigator.state(tick)
        return a,refs
