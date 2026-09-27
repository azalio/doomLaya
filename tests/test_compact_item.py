import copy,unittest
from doomlib.compact_item import compact_item_input


class CompactItemTests(unittest.TestCase):
    state='Current command: pickup #key.\nAvailable mechanisms: lift #12.\nHP 4; armor 2.\nInventory: pistol 90 ammo; shotgun 15 ammo.\nCollected keys: none.\nReachable items: Stimpack#29, BlueCard#key_2.'
    question=dict(type='choice',instructions='Choose an item.',criteria={'29':'Stimpack; reachable; 41.7m.','key_2':'BlueCard; reachable; 45.2m.'})

    def test_projection_keeps_choices_and_resource_facts(self):
        old=copy.deepcopy(self.question);state,q=compact_item_input(self.state,self.question)
        self.assertEqual(q,old);self.assertIsNot(q,self.question)
        self.assertIn('HP 4; armor 2.',state);self.assertIn('shotgun 15 ammo',state)
        self.assertIn('Collected keys: none.',state);self.assertIn('Stimpack#29',state)
        self.assertIn('Health below 35: yes',state);self.assertNotIn('command',state);self.assertNotIn('mechanisms',state)

    def test_missing_or_ambiguous_health_is_rejected(self):
        for state in ('Inventory: pistol 2 ammo.',self.state+'\nHP 80; armor 0.'):
            with self.assertRaises(ValueError):compact_item_input(state,self.question)

    def test_router_executes_a_model_key_choice_even_at_low_health(self):
        from doomlib.question_heads import QuestionHeads
        from tests.test_question_heads import Stub
        model=Stub('key_2');heads=QuestionHeads(model,{'item':model},item_compact_facts=True)
        answer=heads.predict(self.state,{'item':self.question})
        self.assertEqual(answer['answers']['item']['choice'],'key_2')
        self.assertEqual(model.calls,[(compact_item_input(self.state,self.question)[0],{'item':self.question})])


class ItemCategoryTests(unittest.TestCase):
    question=CompactItemTests.question
    state=CompactItemTests.state+'\nItems: Stimpack#29 [Health] 41.7m; BlueCard#key_2 [Key] 45.2m.'

    def test_observed_categories_do_not_change_item_ids_or_resource_facts(self):
        from doomlib.compact_item import category_item_input
        state,q=category_item_input(self.state,self.question)
        self.assertEqual(state,compact_item_input(self.state,self.question)[0])
        self.assertEqual(list(q['criteria']),list(self.question['criteria']))
        self.assertEqual(q['criteria']['29'],'41.7m Health Stimpack reachable')
        self.assertEqual(q['criteria']['key_2'],'45.2m Key BlueCard reachable')

    def test_missing_or_mismatched_category_fails(self):
        from doomlib.compact_item import category_item_input
        for state in (CompactItemTests.state,self.state.replace('Stimpack#29','BlueCard#29')):
            with self.assertRaises(ValueError):category_item_input(state,self.question)

    def test_category_router_keeps_a_model_choice_even_when_health_is_low(self):
        from doomlib.question_heads import QuestionHeads
        from tests.test_question_heads import Stub
        model=Stub('key_2');heads=QuestionHeads(model,{'item':model},item_category_facts=True)
        answer=heads.predict(self.state,{'item':self.question})
        self.assertEqual(answer['answers']['item']['choice'],'key_2')


if __name__=='__main__':unittest.main()
