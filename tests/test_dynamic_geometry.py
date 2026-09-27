"""Opening an automatic monster closet must make its floor navigable immediately."""
import unittest
from types import SimpleNamespace
from doomlib.navigation import Navigator


def room(x1,x2,floor=0,ceiling=96):
    points=[(x1,0),(x2,0),(x2,128),(x1,128),(x1,0)]
    return SimpleNamespace(floor_height=floor,ceiling_height=ceiling,lines=[SimpleNamespace(x1=a,y1=b,x2=c,y2=d,is_blocking=False) for (a,b),(c,d) in zip(points,points[1:])])

class DynamicGeometryTest(unittest.TestCase):
    def test_opening_and_closing_unmapped_sector_updates_connectivity(self):
        sectors=[room(0,128),room(128,192,ceiling=0),room(192,320)]
        nav=Navigator(sectors,doors=[{'sector':99,'key':None}]);start=(64,64);goal=(256,64)
        self.assertNotIn(nav.nearest(goal),nav.reachable(start))
        nav.path=[nav.nearest(start)];nav.failed_request=('old',);nav.blocked={('old','edge')}
        sectors[1].ceiling_height=64
        self.assertEqual(nav.update_geometry(sectors),[1])
        self.assertIn(nav.nearest(goal),nav.reachable(start))
        self.assertEqual(nav.path,[]);self.assertIsNone(nav.failed_request);self.assertEqual(nav.blocked,set())
        count=sum(map(len,nav.body_sectors.values()))
        self.assertEqual(nav.update_geometry(sectors),[])
        self.assertEqual(sum(map(len,nav.body_sectors.values())),count)
        sectors[1].ceiling_height=0;self.assertEqual(nav.update_geometry(sectors),[1])
        self.assertNotIn(nav.nearest(goal),nav.reachable(start))

    def test_lowered_floor_can_open_previously_excluded_area(self):
        sectors=[room(0,128),room(128,192,floor=80),room(192,320)]
        nav=Navigator(sectors,doors=[{'sector':99,'key':None}])
        self.assertNotIn(nav.nearest((256,64)),nav.reachable((64,64)))
        sectors[1].floor_height=0;nav.update_geometry(sectors);nav.update_floors(sectors)
        self.assertIn(nav.nearest((256,64)),nav.reachable((64,64)))
