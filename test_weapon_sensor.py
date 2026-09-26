"""Engine fixtures for exact weapon observations; granted items are test setup only."""
import unittest
from types import SimpleNamespace
from agent import make_game,Sensors,BUTTONS
from executor import Executor


class WeaponSensorTest(unittest.TestCase):
    def setUp(self):
        args=SimpleNamespace(map='MAP02',skill=3,seed=54,show=False,sound=False,weapon_sensor=True)
        self.game=make_game(args,no_monsters=True)
        self.game.make_action([0]*len(BUTTONS),12)
        self.sensor=Sensors(weapon_sensor=True)
        self.controller=Executor();self.tick=0

    def tearDown(self):self.game.close()

    def state(self):return self.sensor.read(self.game,self.tick)[1]

    def grant(self,*weapons):
        for weapon in weapons:self.game.send_game_command('give '+weapon)
        self.game.make_action([0]*len(BUTTONS),2)

    def equip(self,weapon):
        self.controller.accept(dict(action='wait',target=None,weapon=weapon,decision_id=self.tick+1,command='wait'),self.tick)
        for _ in range(105):
            state=self.state();buttons,_=self.controller.act(state,self.tick)
            self.game.make_action(buttons,1);self.tick+=1
        self.assertEqual(self.state()['weapon'],weapon)
        self.assertEqual(self.state()['weapon_slot'],3)

    def test_shared_slot_does_not_conflate_ownership(self):
        self.grant('SuperShotgun')
        state=self.state()
        self.assertEqual(state['inventory']['3']['owned'],0)
        self.assertEqual(state['inventory']['8']['owned'],1)
        self.equip(8)

    def test_each_model_requested_shotgun_is_selected_and_consumes_its_own_ammo(self):
        self.grant('Shotgun','SuperShotgun')
        for weapon,cost in [(8,2),(3,1),(8,2)]:
            self.equip(weapon);before=self.state()['ammo']
            buttons=[0]*len(BUTTONS);buttons[5]=1;self.game.make_action(buttons,1)
            self.game.make_action([0]*len(BUTTONS),70)
            self.assertEqual(before-self.state()['ammo'],cost)


if __name__=='__main__':unittest.main()
