"""Удержание видимой цели и выбор оружия из настоящего инвентаря."""
import math

WEAPON_NAMES = {1:'melee',2:'pistol',3:'shotgun',4:'chaingun',5:'rocket_launcher',6:'plasma_rifle',7:'BFG',8:'super_shotgun',9:'chainsaw'}

WEAPON_SLOTS={**{i:i for i in range(1,8)},8:3,9:1}
AMMO_COST={1:0,2:1,3:1,4:1,5:1,6:1,7:40,8:2,9:0}


def target_bearing(target, s):
    angle=math.degrees(math.atan2(target['y']-s['y'],target['x']-s['x']))
    return -((angle-s['angle']+180)%360-180)


class Combat:
    def __init__(self):
        self.target=None
        self.confirmed_kills=set()
        self.last_shot_id=None
        self.last_seen=-1000
        self.last_kills=0
        self.last_switch=-1000
        self.desired=2
        self.side=1

    def track(self,s,tick):
        if s['kills']>self.last_kills and self.last_shot_id is not None:
            self.confirmed_kills.add(self.last_shot_id)
        visible={e['id']:e for e in s['enemies'] if e['id'] not in self.confirmed_kills}
        if self.target and (self.target['id'] in s['dead_ids'] or self.target['id'] in self.confirmed_kills or
                            (s['kills']>self.last_kills and self.target['id'] not in visible)):
            self.target=None
        self.last_kills=s['kills']
        if self.target and self.target['id'] in visible:
            self.target=dict(visible[self.target['id']])
            self.last_seen=tick
        elif self.target and tick-self.last_seen>140:
            self.target=None
        if not self.target and visible:
            self.target=dict(min(visible.values(),key=lambda e:e['distance']+abs(e['bearing'])/20))
            self.last_seen=tick
        if self.target:
            target=dict(self.target)
            target['bearing']=target.get('aim_bearing',target_bearing(target,s)) if target['id'] in visible else target_bearing(target,s)
            target['distance']=math.hypot(target['x']-s['x'],target['y']-s['y'])/32
            target['visible']=target['id'] in visible
            return target
        return None

    def weapon(self,s,target,tick):
        inventory=s['inventory']
        distance=target['distance'] if target else 15
        order=[6,4,3,2,1] if distance>9 else [6,3,4,2,1]
        if target and target['visible'] and distance>10 and s['walls']['ahead']>6:
            order.insert(1,5)
        if len(s['enemies'])>=3 and distance>8:
            order.insert(0,7)
        usable={int(k):v for k,v in inventory.items() if v['owned'] and
                (int(k)==1 or v['ammo'] >= (40 if int(k)==7 else 1))}
        preferred=next((slot for slot in order if slot in usable),1)
        current=s['weapon']
        # Не дёргаем оружие при колебаниях расстояния около порога.
        if tick-self.last_switch<35 and current in usable:
            preferred=self.desired if self.desired in usable else preferred
        self.desired=preferred
        selection=0
        if current!=preferred and tick-self.last_switch>=12:
            selection=preferred
            self.last_switch=tick
        return preferred,selection

    def act(self,s,target,tactic,tick):
        b=target['bearing']
        a=[0.,0.,0.,0.,max(-9,min(9,b)),0.,0.]
        refs=['combat_lock']
        if target['visible']:
            a[5]=float(abs(b)<5 and s['ammo']>0)
            if a[5]:self.last_shot_id=target['id']
            # Сначала завершить доворот, затем подходить/стрейфить, не пробегая
            # мимо монстра. Навигация не меняет направление прицела.
            if abs(b)<25:
                if tactic=='retreat' and s['hp']<35:
                    a[1]=1
                elif target['distance']>13 or (s['weapon']==1 and target['distance']>1.5):
                    a[0]=1
                elif tick%70<35:
                    if tactic=='strafe_left_fire':self.side=-1
                    elif tactic=='strafe_right_fire':self.side=1
                    elif tick%70==0:self.side=-self.side
                    a[2 if self.side<0 else 3]=1
            refs.append('aim')
        else:
            a[0]=float(abs(b)<25 and target['distance']>1)
            refs.append('pursue_last_seen')
        return a,refs
