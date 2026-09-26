"""Память полезных предметов и проверяемый прирост ресурсов игрока."""
import math

WEAPONS={'Shotgun':3,'SuperShotgun':8,'Chaingun':4,'PlasmaRifle':6,'RocketLauncher':5,'BFG9000':7,'Chainsaw':9}


def weapon_slot(name,inventory):
    slot=WEAPONS.get(name)
    if slot==8 and '8' not in inventory:return 3
    if slot==9 and '9' not in inventory:return 1
    return slot


def utility(item,s):
    name,category=item['name'],item['category']
    if category=='Weapon':
        slot=weapon_slot(name,s['inventory'])
        if slot and (not s['inventory'][str(slot)]['owned'] or
                     (name in ('SuperShotgun','Chainsaw') and slot in (1,3) and s['inventory'][str(slot)]['owned']<2)):
            return 100
        return 0
    if category=='Key':return 85
    if category=='Health':
        limit=200 if name in ('HealthBonus','Soulsphere','SoulSphere','Megasphere','MegaSphere') else 100
        return (150 if s['hp']<35 else 70 if s['hp']<75 else 20) if s['hp']<limit else 0
    if category=='Armor':
        limit=100 if name in ('GreenArmor','BasicArmor') else 200
        return (65 if s['armor']<75 else 20) if s['armor']<limit else 0
    if category=='Ammo':
        lower=name.lower()
        slot,limit=(3,50) if 'shell' in lower else ((5,50) if 'rocket' in lower else ((6,300) if 'cell' in lower else (2,200)))
        ammo=s['inventory'][str(slot)]['ammo']
        if ammo>=limit:return 0
        owned=s['inventory'][str(slot)]['owned'] or (slot==2 and s['inventory']['4']['owned'])
        return (80 if ammo<10 else 35) if owned else 10
    if category=='Powerup':return 40
    return 0


class Items:
    def __init__(self):
        self.known={}
        self.unavailable=set()
        self.target=None
        self.started=0
        self.previous=None

    def reject_target(self):
        if self.target is not None:
            self.unavailable.add(self.target)
            self.known.pop(self.target,None)
            self.target=None

    def update(self,s,tick):
        visible={i['id']:i for i in s['items']}
        self.known.update({key:dict(i) for key,i in visible.items() if key not in self.unavailable})
        gains={}
        if self.previous:
            for field in ('hp','armor'):
                diff=s[field]-self.previous[field]
                if diff>0:gains[field]=diff
            for slot in ('2','3','5','6'):
                diff=s['inventory'][slot]['ammo']-self.previous['inventory'][slot]['ammo']
                if diff>0:gains['ammo_'+slot]=diff
            for slot,entry in s['inventory'].items():
                if entry['owned']>self.previous['inventory'][slot]['owned']:
                    gains['weapon_'+slot]=entry['owned']-self.previous['inventory'][slot]['owned']
        self.previous={'hp':s['hp'],'armor':s['armor'],'inventory':s['inventory']}
        for key,item in list(self.known.items()):
            distance=math.hypot(item['x']-s['x'],item['y']-s['y'])/32
            item['distance']=distance
            if key not in visible and distance<1.1:
                self.unavailable.add(key)
                del self.known[key]
                if self.target==key:self.target=None
        if self.target is not None and (self.target not in self.known or utility(self.known[self.target],s)<=0):
            self.target=None
        if self.target is not None and tick-self.started>175:
            self.unavailable.add(self.target)
            self.known.pop(self.target,None)
            self.target=None
        candidates=[i for i in self.known.values() if utility(i,s)>0 and
                    i['distance']<=(12 if i['category']=='Weapon' else (15 if i['category']=='Health' and s['hp']<35 else 6))]
        if candidates:
            best=max(candidates,key=lambda i:utility(i,s)-i['distance']*1.5)
            urgent=best['category']=='Health' and s['hp']<35
            if self.target is None or urgent:
                if self.target!=best['id']:self.started=tick
                self.target=best['id']
        target=self.known.get(self.target)
        s['resource']={'target':dict(target) if target else None,'gains':gains,'known_items':len(self.known)}
        return target
