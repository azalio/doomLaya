"""Question routing preserves model choices without inspecting game state."""
import unittest
from doomlib.question_heads import QuestionHeads


class Stub:
    def __init__(self,label):self.label=label;self.calls=[]
    def predict(self,state,questions):
        self.calls.append((state,questions))
        return dict(model='laya',answers={name:{'choice':self.label} for name in questions},usage={'input_tokens':len(questions)*11,'output_tokens':0})


class QuestionHeadsTest(unittest.TestCase):
    def test_mixed_batch_preserves_answers_order_state_and_token_accounting(self):
        base=Stub('base');items=Stub('trained');heads=QuestionHeads(base,{'item':items})
        state='HP 100; arbitrary current goal';questions={'combat':{},'item':{},'weapon':{}}
        result=heads.predict(state,questions)
        self.assertEqual(list(result['answers']),list(questions))
        self.assertEqual(result['answers'],{'combat':{'choice':'base'},'item':{'choice':'trained'},'weapon':{'choice':'base'}})
        self.assertEqual(base.calls,[(state,{'combat':{},'weapon':{}})])
        self.assertEqual(items.calls,[(state,{'item':{}})])
        self.assertEqual(result['usage']['input_tokens'],33)

    def test_without_item_uses_only_original_model(self):
        base=Stub('base');items=Stub('trained');heads=QuestionHeads(base,{'item':items})
        heads.predict('unrelated state',{'command':{},'switch':{}})
        self.assertEqual(len(base.calls),1);self.assertEqual(items.calls,[])


    def test_item_projection_does_not_change_other_inputs_or_choices(self):
        shared=Stub('model_choice')
        heads=QuestionHeads(shared,{'item':shared},item_without_goal=True)
        facts='HP 44; armor 1.\nInventory: shotgun 0 ammo.\nPrevious command result: blocked.\nItems: BlueCard#40 10m; Stimpack#29 17m.'
        state='Current command: pickup #40 BlueCard; status executing.\n'+facts
        questions={'command':{'criteria':{'pickup':'collect'}},'item':{'criteria':{'40':'BlueCard','29':'Stimpack'}},'weapon':{'criteria':{'pistol':'loaded'}}}
        result=heads.predict(state,questions)
        self.assertEqual(shared.calls,[(state,{'command':questions['command'],'weapon':questions['weapon']}),(facts,{'item':questions['item']})])
        self.assertEqual(list(result['answers']),list(questions))
        self.assertEqual(result['answers']['item']['choice'],'model_choice')
        self.assertEqual(result['usage']['input_tokens'],33)

    def test_command_projection_preserves_weapon_state_in_shared_head(self):
        shared=Stub('model_choice')
        heads=QuestionHeads(shared,{'command':shared},command_without_goal=True)
        facts='A closed door is 0.7 meters away.\nPrevious command result: blocked.\nHP 100.'
        state='Current command: use_switch #1850; status blocked.\n'+facts
        questions={'command':{'criteria':{'open_door':'Open door','use_switch':'Use switch'}},'weapon':{'criteria':{'shotgun':'loaded'}}}
        result=heads.predict(state,questions)
        self.assertEqual(shared.calls,[(facts,{'command':questions['command']}),(state,{'weapon':questions['weapon']})])
        self.assertEqual(result['answers']['command']['choice'],'model_choice')
        self.assertEqual(result['usage']['input_tokens'],22)

    def test_enemy_projection_preserves_shared_weapon_input_and_hidden_choices(self):
        shared=Stub('hidden_enemy')
        heads=QuestionHeads(shared,{'enemy':shared,'weapon':shared},enemy_without_goal=True)
        facts='HP 40.\nEnemies: Zombieman#1 last seen; DoomImp#2 visible.'
        state='Current command: attack #1; status executing.\n'+facts
        questions={'enemy':{'criteria':{'1':'Not visible now','2':'Visible now'}},'weapon':{'criteria':{'shotgun':'loaded'}}}
        result=heads.predict(state,questions)
        self.assertEqual(shared.calls,[(facts,{'enemy':questions['enemy']}),(state,{'weapon':questions['weapon']})])
        self.assertEqual(result['answers']['enemy']['choice'],'hidden_enemy')
        self.assertEqual(result['usage']['input_tokens'],22)

    def test_item_projection_preserves_states_without_previous_command(self):
        items=Stub('choice');heads=QuestionHeads(items,{'item':items},item_without_goal=True)
        state='HP 44.\nItems: Current command: is part of an item description.'
        heads.predict(state,{'item':{}})
        self.assertEqual(items.calls,[(state,{'item':{}})])


class HeadSpecsTest(unittest.TestCase):
    def test_multiple_questions_can_share_one_checkpoint(self):
        from doomlib.question_heads import parse_head_specs
        self.assertEqual(parse_head_specs(['command=models/shared','item=models/shared']),
                         {'command':'models/shared','item':'models/shared'})
        self.assertEqual(parse_head_specs([], 'models/legacy'), {'item':'models/legacy'})

    def test_rejects_ambiguous_and_misspelled_head_routes(self):
        from doomlib.question_heads import parse_head_specs
        for specs,legacy in [(['item=models/new'],'models/old'),(['command=x','command=y'],None),(['typo=x'],None),(['item='],None),(['item'],None)]:
            with self.subTest(specs=specs):
                with self.assertRaises(ValueError):parse_head_specs(specs,legacy)


if __name__=='__main__':unittest.main()
