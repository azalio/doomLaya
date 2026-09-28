import unittest
from doomlib.mission import Mission


class ExitActivationTest(unittest.TestCase):
    def mission(self,use=True):
        return Mission(dict(exits=[dict(center=(216,-632),approach=(216,-672),use=use,secret=False)]))

    def test_use_exit_does_not_stop_navigation_from_back_side(self):
        state=dict(x=225.46,y=-592.65,angle=256.48)
        self.assertIsNone(self.mission().activate(state,12))

    def test_use_exit_activates_from_its_front_side(self):
        state=dict(x=216,y=-672,angle=90)
        buttons=self.mission().activate(state,12)
        self.assertEqual(buttons[6],1)
        self.assertEqual(buttons[0],0)

    def test_walk_exit_keeps_crossing_from_either_side(self):
        for y,angle in ((-672,90),(-592,270)):
            self.assertEqual(self.mission(use=False).activate(dict(x=216,y=y,angle=angle),12)[0],1)


if __name__=='__main__':unittest.main()
