"""Weapon-use audit must derive available upgrades from observed inventory."""
import unittest
from diagnostics.check_weapon_use import analyze


def row(tick,weapon=2,selected=2,episode=0,shells=4,super_owned=False):
    return dict(tick=tick,seconds=tick/35,episode=episode,hp=100,weapon=weapon,
                inventory={'1':dict(owned=1,ammo=0),'2':dict(owned=1,ammo=50),
                           '3':dict(owned=1,ammo=shells),'8':dict(owned=int(super_owned),ammo=shells)},
                execution={'weapon':selected},buttons=[0]*14)


class WeaponAuditTest(unittest.TestCase):
    def test_weak_model_choice_cannot_hide_an_available_upgrade(self):
        result=analyze([row(i) for i in range(70)])
        self.assertEqual(result['max_upgrade_delay_seconds'],2.)
        self.assertEqual(result['max_model_upgrade_choice_delay_seconds'],2.)

    def test_engine_switch_time_is_reported_separately_from_model_choice(self):
        result=analyze([row(i,selected=3) for i in range(21)]+[row(21,weapon=3,selected=3)])
        self.assertEqual(result['max_upgrade_delay_seconds'],.6)
        self.assertEqual(result['max_model_upgrade_choice_delay_seconds'],0.)

    def test_unloaded_or_unowned_stronger_choice_does_not_end_model_delay(self):
        for owned,shells in ((False,4),(True,1)):
            with self.subTest(super_owned=owned,shells=shells):
                result=analyze([row(i,selected=8,shells=shells,super_owned=owned) for i in range(70)])
                self.assertEqual(result['max_model_upgrade_choice_delay_seconds'],2.)

    def test_shared_shell_inventory_and_episode_reset(self):
        rows=[row(i,weapon=3,selected=3,super_owned=True) for i in range(21)]
        rows += [row(i,weapon=3,selected=8,episode=1,super_owned=True) for i in range(21,42)]
        rows += [row(42,weapon=3,selected=3,episode=1,super_owned=True,shells=1)]
        result=analyze(rows)
        self.assertEqual(result['max_upgrade_delay_seconds'],.6)
        self.assertEqual(result['max_model_upgrade_choice_delay_seconds'],.6)


if __name__=='__main__':unittest.main()
