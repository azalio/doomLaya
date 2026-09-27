"""Describe mapped classic DOOM floor damage at the observed player position."""
import struct
from pathlib import Path
from shapely.geometry import LineString,Point,Polygon
from shapely.ops import polygonize,unary_union

DAMAGE={4:20,5:10,7:5,16:20}


def mapped_hazards(wad,name):
    data=Path(wad).read_bytes();count,offset=struct.unpack_from('<ii',data,4)
    entries=[struct.unpack_from('<ii8s',data,offset+i*16) for i in range(count)]
    index=next(i for i,(_,_,n) in enumerate(entries) if n.rstrip(b'\0').decode()==name.upper())
    start,size,_=next(e for e in entries[index+1:index+11] if e[2].rstrip(b'\0')==b'SECTORS')
    return [dict(sector=i,special=s[-2],damage_per_period=DAMAGE[s[-2]],period_ticks=32,texture=s[2].rstrip(b'\0').decode())
            for i,s in enumerate(struct.iter_unpack('<hh8s8shhh',data[start:start+size])) if s[-2] in DAMAGE]


class FloorHazards:
    def __init__(self,wad,name,sectors):
        self.areas=[]
        for metadata in mapped_hazards(wad,name):
            sector=sectors[metadata['sector']]
            lines=[LineString([(l.x1,l.y1),(l.x2,l.y2)]) for l in sector.lines if (l.x1,l.y1)!=(l.x2,l.y2)]
            polygons=list(polygonize(lines))
            polygons=[p for p in polygons if not any(p is not q and Polygon(q.exterior).contains(p.representative_point()) for q in polygons)]
            self.areas.append((metadata,unary_union(polygons)))

    def observe(self,state,sectors):
        point=Point(state['x'],state['y'])
        active=[dict(m) for m,area in self.areas if area.covers(point) and abs(state['z']-sectors[m['sector']].floor_height)<.5]
        return dict(mapped_damaging_floor=bool(active),damage_per_period=max((m['damage_per_period'] for m in active),default=0),sectors=active)
