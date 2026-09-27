import copy,unittest
from doomlib.compact_weapon import compact_weapon_input
from training.build_map3_compact_weapon import synthetic


class CompactWeaponTests(unittest.TestCase):
    def test_projection_retains_all_weapon_choices_and_relevant_observations(self):
        row=next(synthetic('train'));before=copy.deepcopy(row['question'])
        state,q=compact_weapon_input(row['state']+'\nAvailable mechanisms: lift #1.',row['question'])
        self.assertEqual(q,before);self.assertNotIn('mechanisms',state);self.assertIn('Inventory:',state);self.assertIn('Enemies:',state)
        self.assertNotIn('Current command:',state)

    def test_empty_bullets_do_not_displace_a_loaded_shotgun_with_rockets(self):
        matches=[]
        for row in synthetic('validation'):
            q=row['question']['criteria']
            if all(key in q for key in ('shotgun','chaingun','rocket_launcher')) and 'Loaded: no' in q['chaingun'] and 'Loaded: yes' in q['shotgun'] and 'Loaded: yes' in q['rocket_launcher']:matches.append(row)
        self.assertTrue(matches);self.assertTrue(all(row['label']=='shotgun' for row in matches))

    def test_missing_or_duplicate_inventory_fails(self):
        row=next(synthetic('train'))
        with self.assertRaises(ValueError):compact_weapon_input('HP 7;',row['question'])
        with self.assertRaises(ValueError):compact_weapon_input(row['state']+'\nInventory: shotgun 14 ammo.',row['question'])

    def test_question_router_preserves_model_output_and_all_weapon_options(self):
        from doomlib.question_heads import QuestionHeads
        from tests.test_question_heads import Stub
        row=next(synthetic('train'));model=Stub('pistol');heads=QuestionHeads(model,{'weapon':model},weapon_compact_facts=True)
        result=heads.predict(row['state'],{'weapon':row['question']})
        self.assertEqual(model.calls,[(compact_weapon_input(row['state'],row['question'])[0],{'weapon':row['question']})])
        self.assertEqual(result['answers']['weapon']['choice'],'pistol')
