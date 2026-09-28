"""The movement ablation must preserve all other teacher decisions."""
from types import SimpleNamespace
import unittest

try:
    import vizdoom
except ImportError:
    vizdoom = None


@unittest.skipUnless(vizdoom, 'ViZDoom is needed by the offline teacher')
class TeacherMovementProbeTest(unittest.TestCase):
    def test_changes_only_movement_and_does_not_mutate_original(self):
        from diagnostics.probe_teacher_movement import substitute_movement
        original = dict(command='attack', enemy='17', weapon='shotgun', movement='backward')
        controller = SimpleNamespace(directive={'movement': 'strafe_left'}, navigator=SimpleNamespace(
            movement_clearance=lambda state: {'left': 8, 'right': 4, 'back': 9}))
        seen = []
        def policy(enemies, clearance, current):
            seen.append((enemies, clearance, current))
            return 'strafe_left'
        label = substitute_movement(lambda *args: dict(original), policy)
        packet = {'targets': {'enemy': {'17': {'name': 'DoomImp', 'distance': 6}}}}
        self.assertEqual(label(packet, {}, controller, {}, ''), dict(original, movement='strafe_left'))
        self.assertEqual(original['movement'], 'backward')
        self.assertEqual(seen[0][2], 'strafe_left')
        self.assertEqual(seen[0][0], list(packet['targets']['enemy'].values()))

    def test_does_not_add_movement_to_navigation(self):
        from diagnostics.probe_teacher_movement import substitute_movement
        def fail(*args):
            self.fail('Movement policy must not be called for navigation')
        label = substitute_movement(lambda *args: {'command': 'pickup', 'item': '2'}, fail)
        self.assertEqual(label({}, {}, None, {}, ''), {'command': 'pickup', 'item': '2'})


if __name__ == '__main__':
    unittest.main()
