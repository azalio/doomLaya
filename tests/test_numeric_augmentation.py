import unittest
from training.numeric_augmentation import examples
from doomlib.numeric_command import features, feature_names


class NumericAugmentationTests(unittest.TestCase):
    def test_seeded_physical_observations_have_valid_actions_and_schema(self):
        names={'Medikit':'Health','Shotgun':'Weapon','GreenArmor':'Armor','Clip':'Ammo','BlueCard':'Key'}
        rows=list(examples(names,200,10))
        self.assertEqual(rows,list(examples(names,200,10)))
        self.assertEqual(len(rows),200)
        self.assertGreaterEqual(len({r['label'] for r in rows}),5)
        for row in rows:
            self.assertIn(row['label'],row['question']['criteria'])
            values=features(row,sorted(names))
            self.assertEqual(len(values),len(feature_names(sorted(names))))
            self.assertNotIn('Current command:',row['state'])
        self.assertTrue(any('Previous command result: A closed door blocks movement' in r['state'] for r in rows))

    def test_wide_inventory_covers_observed_late_level_ammo(self):
        rows=list(examples({'Shotgun':'Weapon','Shell':'Ammo'},1000,91,include_items=True,broad_inventory=True))
        inventories=[r['packet']['observation']['inventory'] for r in rows]
        self.assertGreaterEqual(max(v['3']['ammo'] for v in inventories),50)
        self.assertGreaterEqual(max(v['2']['ammo'] for v in inventories),190)
        self.assertGreater(max(r['packet']['observation']['hp'] for r in rows),150)
        self.assertTrue(all(0<=v['3']['ammo']<=50 for v in inventories))

    def test_wide_mechanisms_covers_the_observed_map03_range(self):
        rows=list(examples({'Shotgun':'Weapon'},500,91,include_items=True,broad_mechanisms=True))
        counts={len(r['packet']['targets']['switch']) for r in rows}
        self.assertEqual(counts,set(range(13)))
        for row in rows:
            self.assertIn(row['label'],row['question']['criteria'])
