"""Поиск проходимого маршрута по секторам ViZDoom с памятью посещённых областей."""
from collections import Counter
import heapq
import math

import numpy as np
from shapely import contains_xy, intersects_xy
from shapely.geometry import LineString, Polygon
from shapely.ops import polygonize, unary_union

STEP=16
REGION=256


class Navigator:
    def __init__(self,sectors=None,doors=(),teleports=()):
        self.teleports=teleports
        self.portal_edges={}
        self.sector_cells={}
        self.body_sectors={}
        self.sector_heights=[]
        self.closed_unmapped=None
        self.doors=doors
        self.key_blocks={}
        self.sector_blocks={}
        self.locked=set()
        self.keys=None
        self.free=set()
        self.floors={}
        self.regions=Counter()
        self.entered=set()
        self.path=[]
        self.blocked=set()
        self.last_cell=None
        self.last_xy=None
        self.velocity=(0.,0.)
        self.last_region=None
        self.last_new_tick=0
        self.goal_kind=None
        self.exhausted=False
        self.objective=None
        self.requested=None
        self.walk=None
        self.steering_target=None
        self.failed_request=None
        self.retry_tick=0
        if sectors is not None:self.configure(sectors)

    def configure(self,sectors):
        # Rebuilding geometry must not accumulate old body/door memberships.
        self.sector_cells={};self.body_sectors={};self.sector_blocks={};self.key_blocks={}
        self.portal_edges={}
        mapped_doors={d['sector'] for d in self.doors}
        self.closed_unmapped={i for i,s in enumerate(sectors) if i not in mapped_doors and s.ceiling_height-s.floor_height<56}
        areas=[]
        records=[]
        walls=[]
        for sector_id,sector in enumerate(sectors):
            lines=[LineString([(l.x1,l.y1),(l.x2,l.y2)]) for l in sector.lines if (l.x1,l.y1)!=(l.x2,l.y2)]
            polygons=list(polygonize(lines))
            # Внутреннее кольцо другого сектора не превращаем в пол текущего.
            polygons=[p for p in polygons if not any(p is not q and Polygon(q.exterior).contains(p.representative_point()) for q in polygons)]
            if not polygons:continue
            area=unary_union(polygons)
            height=sector.ceiling_height-sector.floor_height
            door=sector_id in {d["sector"] for d in self.doors} if self.doors else height<=8 and len(sector.lines)<=8 and max(area.bounds[2]-area.bounds[0],area.bounds[3]-area.bounds[1])<=256
            if height>=56 or door:
                areas.append(area)
                records.append((area,float(sector.floor_height),sector_id))
            walls.extend(LineString([(l.x1,l.y1),(l.x2,l.y2)]) for l in sector.lines if l.is_blocking)
        walk=unary_union(areas).buffer(-18)
        if walls:walk=walk.difference(unary_union(walls).buffer(18))
        self.walk=walk
        xmin,ymin,xmax,ymax=walk.bounds
        gx,gy=np.meshgrid(np.arange(math.floor(xmin/STEP),math.ceil(xmax/STEP)+1),np.arange(math.floor(ymin/STEP),math.ceil(ymax/STEP)+1))
        xx,yy=(gx+.5)*STEP,(gy+.5)*STEP
        mask=contains_xy(walk,xx,yy)
        self.sector_heights=[float(s.floor_height) for s in sectors]
        for area,floor,sector_id in records:
            # Collision uses the player's full radius, including higher stair corners.
            occupied=intersects_xy(area.buffer(16),xx,yy)&mask
            nodes=list(zip(gx[occupied].tolist(),gy[occupied].tolist()))
            self.sector_cells.setdefault(sector_id,[]).extend(nodes)
            for node in nodes:self.body_sectors.setdefault(node,[]).append(sector_id)
            if any(d['sector']==sector_id for d in self.doors):
                blocked=intersects_xy(area.buffer(16),xx,yy)&mask
                self.sector_blocks[sector_id]=set(zip(gx[blocked].tolist(),gy[blocked].tolist()))
            required={d['key'] for d in self.doors if d['sector']==sector_id and d['key']}
            for key in required:
                blocked=intersects_xy(area.buffer(16),xx,yy)&mask
                self.key_blocks.setdefault(key,set()).update(zip(gx[blocked].tolist(),gy[blocked].tolist()))
        self.free=set(zip(gx[mask].astype(int).tolist(),gy[mask].astype(int).tolist()))
        self.floors={node:max(self.sector_heights[i] for i in self.body_sectors[node]) for node in self.free}
        for portal in self.teleports:
            entry,exit=self.nearest(portal['entry']),self.nearest(portal['destination'])
            if entry is not None and exit is not None:self.portal_edges[entry]=(exit,portal['cross'])

    @staticmethod
    def point(key):
        return ((key[0]+.5)*STEP,(key[1]+.5)*STEP)

    def nearest(self,xy):
        key=(math.floor(xy[0]/STEP),math.floor(xy[1]/STEP))
        if key in self.free:return key
        nearby=[(x,y) for x in range(key[0]-4,key[0]+5) for y in range(key[1]-4,key[1]+5) if (x,y) in self.free]
        return min(nearby,key=lambda p:math.dist(xy,self.point(p))) if nearby else None

    def pickup_point(self,item):
        """Find physical contact with the selected item, including its observed height."""
        xy=(item['x'],item['y']);node=self.nearest(xy)
        if 'z' not in item or node is None or self.floors[node]<=item['z']+8:return xy
        candidates=[(x,y) for x in range(node[0]-2,node[0]+3) for y in range(node[1]-2,node[1]+3)
                    if (x,y) in self.free and (x,y) not in self.locked
                    and item['z']-56<self.floors[(x,y)]<=item['z']+8
                    and math.dist(xy,self.point((x,y)))<=30]
        return self.point(min(candidates,key=lambda n:math.dist(xy,self.point(n)))) if candidates else xy

    def observe(self,s,tick):
        keys=frozenset(s.get('keys',()))
        signature=(keys,tuple(s.get('closed_remote_doors',())))
        if signature!=self.keys:
            self.keys=signature
            self.locked=set().union(*(cells for key,cells in self.key_blocks.items() if key not in keys),
                                    *(self.sector_blocks.get(i,set()) for i in s.get('closed_remote_doors',())))
            self.path=[]
            self.failed_request=None
        xy=(s['x'],s['y'])
        self.velocity=(xy[0]-self.last_xy[0],xy[1]-self.last_xy[1]) if self.last_xy is not None and math.dist(xy,self.last_xy)<=128 else (0.,0.)
        if self.last_xy is not None and math.dist(xy,self.last_xy)>128:
            self.path=[];self.failed_request=None;self.steering_target=None
        self.last_xy=xy
        region=(math.floor(xy[0]/REGION),math.floor(xy[1]/REGION))
        if region!=self.last_region:
            self.regions[region]+=1
            self.last_region=region
        here=self.nearest(xy)
        if here not in self.entered:
            self.entered.add(here)
            self.last_new_tick=tick
        self.last_cell=here

    def neighbors(self,node):
        if node in self.portal_edges:
            yield self.portal_edges[node][0],64
        for dx,dy in [(1,0),(-1,0),(0,1),(0,-1),(1,1),(-1,1),(1,-1),(-1,-1)]:
            nxt=(node[0]+dx,node[1]+dy)
            if nxt not in self.free or nxt in self.locked or (node,nxt) in self.blocked:continue
            if dx and dy and ((node[0]+dx,node[1]) not in self.free or (node[0],node[1]+dy) not in self.free):continue
            diff=self.floors[nxt]-self.floors[node]
            if diff>24:continue
            yield nxt,math.hypot(dx,dy)*STEP

    def update_geometry(self,sectors):
        """Refresh walkable areas when automatic sectors open or close."""
        mapped_doors={d['sector'] for d in self.doors}
        closed={i for i,s in enumerate(sectors) if i not in mapped_doors and s.ceiling_height-s.floor_height<56}
        if self.closed_unmapped is None or closed==self.closed_unmapped:return []
        changed=sorted(closed^self.closed_unmapped)
        self.configure(sectors)
        self.path=[];self.failed_request=None;self.blocked.clear();self.keys=None
        return changed

    def update_floors(self,sectors):
        changed=[]
        for i,sector in enumerate(sectors):
            height=float(sector.floor_height)
            if height!=self.sector_heights[i]:
                changed.append(i)
                self.sector_heights[i]=height
        if changed:
            affected=set().union(*(self.sector_cells.get(i,()) for i in changed))
            for node in affected:self.floors[node]=max(self.sector_heights[i] for i in self.body_sectors[node])
            self.path=[];self.failed_request=None;self.blocked.clear()
        return changed

    def reachable(self,xy):
        start=self.nearest(xy)
        reached={start} if start is not None else set()
        pending=list(reached)
        while pending:
            for node,_ in self.neighbors(pending.pop()):
                if node not in reached:
                    reached.add(node);pending.append(node)
        return reached

    def movement_clearance(self,s,limit=512):
        """Measure body-space clearance; this does not select a movement."""
        if self.walk is None:return {}
        walk=self.walk.buffer(2.1)
        origin=(s['x'],s['y']);result={}
        for name,offset in [('ahead',0),('left',90),('right',-90),('back',180)]:
            angle=math.radians(s['angle']+offset);previous=self.nearest(origin);distance=0
            for step in range(8,limit+1,8):
                point=(origin[0]+step*math.cos(angle),origin[1]+step*math.sin(angle))
                node=self.nearest(point)
                if not walk.covers(LineString([origin,point])) or node is None or previous is None:break
                if node in self.locked or self.floors[node]-self.floors[previous]>24:break
                distance=step;previous=node
            result[name]=distance/32
        return result

    def reject(self,tick):
        if self.path and self.last_cell is not None:
            nxt=self.path[0]
            # Блокируем конкретный неудачный переход, а не целую ветку маршрута.
            self.blocked.add((self.last_cell,nxt))
            self.blocked.add((nxt,self.last_cell))
            if len(self.path)>1:
                self.blocked.add((nxt,self.path[1]))
        self.path=[]
        self.objective=None

    def plan(self,s,tick,specific_xy=None):
        start=self.nearest((s['x'],s['y']))
        if start is None:
            self.exhausted=True
            return
        specific=self.nearest(specific_xy) if specific_xy is not None else None
        if specific_xy is not None and specific is None:
            self.path=[]
            self.exhausted=True
            self.goal_kind='unreachable'
            return
        queue=[(0,start)]
        costs,parent={start:0},{}
        goal=None
        fallback=None
        while queue:
            cost,node=heapq.heappop(queue)
            if cost!=costs[node]:continue
            p=self.point(node)
            region=(math.floor(p[0]/REGION),math.floor(p[1]/REGION))
            if node==specific:
                goal=node
                self.goal_kind='selected_target'
                break
            if region not in self.regions and math.dist(p,(s['x'],s['y']))>=128:
                if specific is None:
                    goal=node
                    self.goal_kind='new_region'
                    break
                if fallback is None:fallback=node
            if specific is None and fallback is None and node not in self.entered and math.dist(p,(s['x'],s['y']))>=128:
                fallback=node
            for nxt,edge in self.neighbors(node):
                nr=(math.floor(self.point(nxt)[0]/REGION),math.floor(self.point(nxt)[1]/REGION))
                proposed=cost+edge+self.regions[nr]*2
                if proposed<costs.get(nxt,float('inf')):
                    costs[nxt],parent[nxt]=proposed,node
                    heapq.heappush(queue,(proposed,nxt))
        if goal is None and specific is None:
            goal=fallback
            if goal is not None:self.goal_kind="new_cell"
        self.path=[]
        if goal is None:
            self.exhausted=True
            self.goal_kind='unreachable' if specific_xy is not None else 'exhausted'
            return
        self.exhausted=False
        self.objective=goal
        while goal!=start:
            self.path.append(goal)
            goal=parent[goal]
        self.path.reverse()

    def clear_segment(self,a,b):
        if self.walk is None or not self.walk.covers(LineString([a,b])):return False
        previous=self.nearest(a)
        for i in range(1,max(2,math.ceil(math.dist(a,b)/8))+1):
            count=max(2,math.ceil(math.dist(a,b)/8))
            point=(a[0]+(b[0]-a[0])*i/count,a[1]+(b[1]-a[1])*i/count)
            node=self.nearest(point)
            if node is None or previous is None:return False
            if node in self.locked or self.floors[node]-self.floors[previous]>24:return False
            if (previous,node) in self.blocked:return False
            previous=node
        return True

    def steer(self,s,tick,objective=None):
        request_key=('point',self.nearest(objective)) if objective is not None else ('explore',)
        if request_key!=self.requested:
            self.path=[]
            self.requested=request_key
        xy=(s['x'],s['y'])
        for entry,(destination,cross) in self.portal_edges.items():
            if destination in self.path[:8] and math.dist(xy,self.point(entry))<64:
                angle=math.degrees(math.atan2(cross[1]-xy[1],cross[0]-xy[0]))
                turn=-((angle-s['angle']+180)%360-180)
                return [float(abs(turn)<25),0,0,0,max(-6,min(6,turn*.7)),0,0],['cross_teleport_on_selected_route']
        # Бой/телепорт может увести далеко от старого пути. Строим путь от новой позиции.
        if self.path and min(math.dist(xy,self.point(p)) for p in self.path[:8])>96:
            self.path=[]
        while self.path and math.dist(self.point(self.path[0]),xy)<22 and self.floors.get(self.path[0],-math.inf)<=s.get('z',math.inf)+24:
            self.path.pop(0)
        # A fall can invalidate a nearby cached waypoint without a large XY jump.
        if self.path and self.walk is not None and not self.clear_segment(xy,self.point(self.path[0])):
            self.path=[]
        if not self.path:
            request=(self.nearest(xy),request_key)
            if request==self.failed_request and tick<self.retry_tick:
                return [0,0,0,0,0,0,0],['navigation_exhausted']
            self.plan(s,tick,objective)
            if not self.path:
                self.failed_request,self.retry_tick=request,tick+35
            else:self.failed_request=None
        if not self.path:return [0,0,0,0,0,0,0],['navigation_exhausted']
        # Смотрим вперёд вдоль свободного коридора, а не целимся в каждый узел сетки.
        look=0
        for i,node in enumerate(self.path[:12]):
            point=self.point(node)
            if math.dist(point,xy)>96:break
            if self.clear_segment(xy,point):look=i
            else:break
        if look:self.path=self.path[look:]
        target=self.point(self.path[0])
        self.steering_target=target
        angle=math.degrees(math.atan2(target[1]-xy[1],target[0]-xy[0]))
        turn=-((angle-s['angle']+180)%360-180)
        if abs(turn)<1:turn=0
        action=[float(abs(turn)<25),0,0,0,max(-6,min(6,turn*.7)),0,0]
        refs=['waypoint']
        if abs(turn)>=25 and math.hypot(*self.velocity)>1:
            # Release alone preserves Doom momentum and can carry the player off a ledge.
            facing=math.radians(s['angle']);vx,vy=self.velocity
            forward=vx*math.cos(facing)+vy*math.sin(facing)
            right=vx*math.sin(facing)-vy*math.cos(facing)
            action[:4]=[float(forward<-1),float(forward>1),float(right>1),float(right<-1)]
            refs.append('brake_before_route_turn')
        return action,refs

    def state(self,tick):
        points=([self.last_xy]+[self.point(node) for node in self.path]) if self.last_xy is not None and self.path else []
        remaining=sum(math.dist(a,b) for a,b in zip(points,points[1:]))/32 if points else None
        return {'known_cells':len(self.free),'visited_cells':len(self.entered),'regions':len(self.regions),
                'goal_kind':self.goal_kind,'exhausted':self.exhausted,'path_length':len(self.path),
                'remaining_distance':round(remaining,3) if remaining is not None else None,
                'no_new_cell_seconds':round((tick-self.last_new_tick)/35,2),
                'target':list(self.point(self.path[0])) if self.path else None}
