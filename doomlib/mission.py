"""Выходы уровня из LINEDEFS WAD; прохождение только игровыми кнопками."""
import math
import struct
from pathlib import Path


def map_data(wad, name, skill=3):
    data=Path(wad).read_bytes()
    count,offset=struct.unpack_from('<ii',data,4)
    directory=[struct.unpack_from('<ii8s',data,offset+i*16) for i in range(count)]
    index=next(i for i,(_,_,n) in enumerate(directory) if n.rstrip(b'\0').decode()==name.upper())
    lumps={n.rstrip(b'\0').decode():data[p:p+size] for p,size,n in directory[index+1:index+11]}
    vertices=list(struct.iter_unpack('<hh',lumps['VERTEXES']))
    exits=[]
    teleports=[]
    switches=[]
    things=list(struct.iter_unpack("<hhhhh",lumps["THINGS"]))
    key_names={5:('blue','BlueCard'),6:('yellow','YellowCard'),13:('red','RedCard'),38:('red','RedSkull'),39:('yellow','YellowSkull'),40:('blue','BlueSkull')}
    key_markers=[{'id':f'key_{i}','name':key_names[t[3]][1],'color':key_names[t[3]][0],'category':'Key','x':t[0],'y':t[1],'source':'wad'} for i,t in enumerate(things) if t[3] in key_names]
    weapon_names={2001:'Shotgun',82:'SuperShotgun',2002:'Chaingun',2003:'RocketLauncher',2004:'PlasmaRifle',2005:'Chainsaw',2006:'BFG9000'}
    skill_flag=1 if skill<=2 else 2 if skill==3 else 4
    weapon_markers=[{'id':f'weapon_{i}','name':weapon_names[t[3]],'category':'Weapon','x':t[0],'y':t[1],'source':'wad'}
                    for i,t in enumerate(things) if t[3] in weapon_names and t[4]&skill_flag and not t[4]&16]
    sectors=list(struct.iter_unpack("<hh8s8shhh",lumps["SECTORS"]))
    lines=list(struct.iter_unpack("<7H",lumps["LINEDEFS"]))
    sides=list(struct.iter_unpack('<hh8s8s8sH',lumps['SIDEDEFS']))
    door_sectors=set()
    doors=[]
    locks={26:"blue",32:"blue",27:"yellow",34:"yellow",28:"red",33:"red"}
    for index,line in enumerate(lines):
        start,end,flags,special,tag,front,back=line
        if special in (1,26,27,28,31,32,33,34,117,118) and back!=65535:
            door_sectors.add(sides[back][-1])
            a,b=vertices[start],vertices[end]
            doors.append({'line':index,'sector':sides[back][-1],'key':locks.get(special),
                          'a':a,'b':b,'center':((a[0]+b[0])/2,(a[1]+b[1])/2)})
        if special in (61,62,71,103,112,99,133,134,135,136,137):
            a,b=vertices[start],vertices[end];length=math.dist(a,b)
            center=((a[0]+b[0])/2,(a[1]+b[1])/2)
            normal=((b[1]-a[1])/length,-(b[0]-a[0])/length)
            targets=[i for i,sector in enumerate(sectors) if sector[-1]==tag]
            switches.append({'id':index,'kind':'lift' if special==62 else ('floor' if special==71 else 'door'),'name':'Lift' if special==62 else ('Floor switch' if special==71 else 'Door switch'),'x':center[0],'y':center[1],
                             'board':(center[0]-normal[0]*32,center[1]-normal[1]*32),
                             'upper_floor':max(sectors[i][0] for i in targets),
                             'approach':(center[0]+normal[0]*40,center[1]+normal[1]*40),
                             'sectors':targets,'key':{99:'blue',133:'blue',134:'red',135:'red',136:'yellow',137:'yellow'}.get(special)})
            if special==61:switches[-1]['repeatable']=True
            if special==71:switches[-1]['initial_floors']={i:sectors[i][0] for i in targets}
        if special in (39,97):
            from shapely.geometry import LineString,Point
            from shapely.ops import polygonize
            destinations=[]
            for sector_id,sector in enumerate(sectors):
                if sector[-1]!=tag:continue
                boundaries=[LineString([vertices[l[0]],vertices[l[1]]]) for l in lines
                            if (l[5]!=65535 and sides[l[5]][-1]==sector_id) or (l[6]!=65535 and sides[l[6]][-1]==sector_id)]
                areas=list(polygonize(boundaries))
                destinations.extend(t[:2] for t in things if t[3]==14 and any(a.covers(Point(t[:2])) for a in areas))
            if destinations:
                a,b=vertices[start],vertices[end];length=math.dist(a,b)
                center=((a[0]+b[0])/2,(a[1]+b[1])/2)
                normal=((b[1]-a[1])/length,-(b[0]-a[0])/length)
                teleports.append({'line':index,'entry':(center[0]+normal[0]*32,center[1]+normal[1]*32),
                                  'cross':(center[0]-normal[0]*32,center[1]-normal[1]*32),'destination':destinations[0]})
        if special not in (11,51,52,124):continue
        a,b=vertices[start],vertices[end]
        center=((a[0]+b[0])/2,(a[1]+b[1])/2)
        length=math.dist(a,b)
        normal=((b[1]-a[1])/length,-(b[0]-a[0])/length)
        exits.append({'line':index,'special':special,'center':center,
                      'approach':(center[0]+normal[0]*40,center[1]+normal[1]*40),
                      'use':special in (11,51),'secret':special in (51,124)})
    exit_sectors={sides[side][-1] for e in exits if not e['secret'] for side in lines[e['line']][5:] if side!=65535}
    for switch in switches:
        if switch['kind']=='floor' and exit_sectors.intersection(switch['sectors']):switch['route_exit']=True
    return {'name':name.upper(),'exits':exits,'door_sectors':sorted(door_sectors),'doors':doors,'teleports':teleports,'switches':switches,'key_markers':key_markers,'weapon_markers':weapon_markers}


class Mission:
    def __init__(self,data):
        self.data=data
        self.exit=next((e for e in data['exits'] if not e['secret']),None)
        self.activated_switches=set()
        self.lowered_lifts=set()
        self.used_switches=set()
        self.pending_switches={}

    def annotate_lift_routes(self,navigator):
        """Describe mapped keys connected to a lift's upper platform without descending."""
        for lift in self.data.get('switches',()):
            if lift.get('kind')!='lift':continue
            start=navigator.nearest(lift['board'])
            if start is None:continue
            minimum=lift['upper_floor']-24
            seen={start};pending=[start]
            while pending:
                for node,_ in navigator.neighbors(pending.pop()):
                    if node not in seen and navigator.floors[node]>=minimum:
                        seen.add(node);pending.append(node)
            lift['route_keys']=sorted({key['color'] for key in self.data.get('key_markers',())
                                       if navigator.nearest((key['x'],key['y'])) in seen})

    def note_switch_use(self,switch_id,engine_tick):
        """Record an executed USE; consume a one-shot button only after its door opens."""
        self.pending_switches[switch_id]=engine_tick

    def observe(self,s,sectors):
        closed=[];switches=[]
        for switch in self.data.get('switches',[]):
            phase='call'
            if switch.get('kind')=='lift':
                sector=sectors[switch['sectors'][0]]
                floor=sector.floor_height
                if floor<switch['upper_floor']-4:self.lowered_lifts.add(switch['id'])
                xs=[l.x1 for l in sector.lines]+[l.x2 for l in sector.lines]
                ys=[l.y1 for l in sector.lines]+[l.y2 for l in sector.lines]
                inside=min(xs)+16<s['x']<max(xs)-16 and min(ys)+16<s['y']<max(ys)-16
                if inside and switch['id'] in self.lowered_lifts:
                    phase='ride'
                    if floor>=switch['upper_floor']-1 and s.get('z',floor)>=switch['upper_floor']-1:self.activated_switches.add(switch['id'])
                elif floor<=s.get('z',floor)+24 and switch['id'] in self.lowered_lifts:phase='board'
            elif switch.get('kind')=='floor':
                if any(sectors[i].floor_height<height-.5 for i,height in switch['initial_floors'].items()):self.activated_switches.add(switch['id'])
            else:
                opened=any(sectors[i].ceiling_height-sectors[i].floor_height>=56 for i in switch['sectors'])
                pressed=self.pending_switches.get(switch['id'])
                if pressed is not None:
                    if s.get('engine_tic',0)-pressed>105:self.pending_switches.pop(switch['id'])
                    elif opened:
                        self.used_switches.add(switch['id']);self.pending_switches.pop(switch['id'])
                if opened or (switch['id'] in self.used_switches and not switch.get('repeatable')):self.activated_switches.add(switch['id'])
                else:self.activated_switches.discard(switch['id'])
                closed.extend(i for i in switch['sectors'] if sectors[i].ceiling_height-sectors[i].floor_height<56)
            switches.append(dict(switch,phase=phase,activated=switch['id'] in self.activated_switches and (switch.get('kind')!='lift' or s.get('z',0)>=switch['upper_floor']-24),
                                 distance=math.dist((s['x'],s['y']),(switch['x'],switch['y']))/32,
                                 locked=bool(switch['key'] and switch['key'] not in s.get('keys',()))))
        s['switches']=switches
        s['closed_remote_doors']=sorted(set(closed))

    def objective(self):
        return self.exit['approach'] if self.exit else None

    def activate(self,s,tick):
        if not self.exit:return None
        center=self.exit['center']
        if math.dist((s['x'],s['y']),center)>60:return None
        if self.exit['use']:
            # USE specials only respond from the linedef front side. Keep
            # navigating to the mapped approach when close from behind.
            approach=self.exit['approach']
            side=(s['x']-center[0])*(approach[0]-center[0])+(s['y']-center[1])*(approach[1]-center[1])
            if side<=0:return None
        angle=math.degrees(math.atan2(center[1]-s['y'],center[0]-s['x']))
        turn=-((angle-s['angle']+180)%360-180)
        return [float(not self.exit['use'] and abs(turn)<15),0,0,0,
                max(-6,min(6,turn)),0,float(self.exit['use'] and abs(turn)<8 and tick%12==0)]
