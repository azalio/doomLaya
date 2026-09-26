"""Regression checks for explicit-target training supervision."""
import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from policy import request
from training.build_committed_dataset import examples


class TrainingExamplesTest(unittest.TestCase):
    def packet(self):
        s=json.loads((Path(__file__).parent/'fixtures/authority-state.json').read_text())
        s['door']=None
        item=s['items'][0]
        s['execution']=dict(action='pickup',target_id=item['id'],status='executing',movement=None)
        return request(s,{item['id']:item},SimpleNamespace(exit=None)),item

    def test_explicit_mode_supervises_target_even_when_the_goal_is_unchanged(self):
        packet,item=self.packet();gold=dict(command='collect_'+str(item['id']),weapon='pistol')
        original={r['kind']:r for r in examples(packet,gold,'test',0,0)}
        self.assertEqual(original['command']['label'],'continue')
        self.assertNotIn('item',original)
        dense={r['kind']:r for r in examples(packet,gold,'test',0,0,explicit_actions=True)}
        self.assertEqual(dense['command']['label'],'pickup')
        self.assertNotIn('continue',dense['command']['question']['criteria'])
        self.assertEqual(dense['item']['label'],str(item['id']))
        expected={str(c['target']['id']) for c in packet['commands'].values() if c['action']=='pickup'}
        self.assertEqual(set(dense['item']['question']['criteria']),expected)
        self.assertEqual(dense['command']['state'],original['command']['state'])

    def test_previous_goal_pairs_preserve_the_item_label_and_world(self):
        from training.build_goal_invariant_items import change_goal
        row=dict(kind='item',label='36',source_type='offline_teacher',
                 state='Current command: attack #9; status unavailable.\nPrevious command result: Selected enemy disappeared.\nHP 59; armor 2.\nInventory: shotgun 1 ammo.\nItems: Medikit#36 9.4m; Shell#33 23.1m.',
                 question=dict(criteria={'36':'Medikit; reachable; 9.4m.','33':'Shell; reachable; 23.1m.'}))
        original=json.loads(json.dumps(row))
        same=change_goal(row,'36');other=change_goal(row,'33')
        self.assertEqual(row,original)
        self.assertEqual(same['label'],other['label'])
        self.assertEqual(same['label'],'36')
        self.assertEqual(same['question'],row['question'])
        self.assertEqual(other['question'],row['question'])
        self.assertEqual(same['state'].splitlines()[1:],other['state'].splitlines()[1:])
        self.assertIn('pickup #36 Medikit 9.4m; status executing.',same['state'])
        self.assertIn('pickup #33 Shell 23.1m; status executing.',other['state'])
        self.assertNotIn('Selected enemy disappeared',same['state'])
        self.assertTrue(same['synthetic'])

    def test_late_route_pairs_cover_reachable_key_ammo_and_healing(self):
        import random
        from training.build_late_route_curriculum import paired_examples
        rows=paired_examples(random.Random(52),17)
        groups={}
        for row in rows:groups.setdefault(row['pair_variant'],{})[row['kind']]=row
        loaded=groups['loaded']['item'];empty=groups['empty_shells']['item']
        self.assertEqual(loaded['question'],empty['question'])
        self.assertEqual([s for s in loaded['state'].splitlines() if not s.startswith('Inventory:')],
                         [s for s in empty['state'].splitlines() if not s.startswith('Inventory:')])
        for variant,name in [('loaded','YellowCard'),('empty_shells','ShellBox'),('critical_health','Medikit')]:
            row=groups[variant]['item']
            self.assertTrue(row['question']['criteria'][row['label']].startswith(name+'; reachable;'))
            self.assertEqual(groups[variant]['command']['label'],'pickup')
        self.assertEqual(groups['blocked_key']['command']['label'],'use_switch')
        self.assertEqual(groups['all_keys']['command']['label'],'exit')
        self.assertTrue(all(row['synthetic'] for row in rows))

    def test_mechanism_goal_pairs_preserve_the_boarding_target_and_world(self):
        from training.build_goal_invariant_switches import change_goal
        row=dict(kind='switch',label='805',state='Current command: use_switch #805 Lift 1.0m; status executing.\nHP 100; armor 0.\nAvailable mechanisms: lift #805 phase board 1.0m; door switch #662 20.0m.',question=dict(criteria={'805':'Call, board and ride lift #805. Phase: board. Distance 1.0m.','662':'Activate door switch #662. Distance 20.0m.'}))
        before=json.loads(json.dumps(row));same=change_goal(row,'805');other=change_goal(row,'662')
        self.assertEqual(row,before)
        self.assertEqual(same['label'],other['label'])
        self.assertEqual(same['label'],'805')
        self.assertEqual(same['question'],other['question'])
        self.assertEqual(same['state'].splitlines()[1:],other['state'].splitlines()[1:])
        self.assertIn('use_switch #662 Door switch 20.0m',other['state'])
        self.assertIn('phase board',other['state'])

    def test_recorded_correction_keeps_masked_world_facts_and_option_order(self):
        from training.build_recorded_commands import recorded_row
        original='Reachable items: Shell#1.\nItems: RedCard#5 [Key] 12.4m; Shell#1 [Ammo] 19.5m.'
        question=dict(type='choice',instructions='Choose.',criteria={'use_switch':'Use a mechanism.','pickup':'Collect an available item.'})
        decision=dict(packet=dict(state=original,questions={'command':question}),answers={'command':{'choice':'pickup'}})
        regenerated=dict(kind='command',label='use_switch',state='Items: Shell#1 [Ammo] 19.5m.',question={'criteria':{'pickup':'short'}})
        corrected=recorded_row(regenerated,decision)
        self.assertEqual(corrected['state'],original)
        self.assertEqual(corrected['question'],question)
        self.assertEqual(list(corrected['question']['criteria']),list(question['criteria']))
        self.assertEqual(corrected['label'],'use_switch')
        self.assertEqual(regenerated['state'],'Items: Shell#1 [Ammo] 19.5m.')

    def test_root_goal_variants_keep_world_labels_and_only_available_goals(self):
        from training.build_goal_invariant_commands import change_goal,goal_headers
        row=dict(kind='command',label='pickup',source_type='offline_teacher',
                 state='Current command: attack #9; status unavailable.\nPrevious command result: Enemy disappeared.\nReachable items: Shell#102.\nAvailable mechanisms: lift #805 phase board 2.5m Upper route keys: blue (missing).; door switch #662 42.0m.\nHP 40; armor 0.\nItems: RedCard#5 [Key] 1.0m; Shell#102 [Ammo] 4.6m.',
                 question=dict(criteria={'pickup':'Collect supplies.','use_switch':'Use a mechanism.','attack':'Attack.'}))
        original=json.loads(json.dumps(row));goals=goal_headers(row)
        self.assertEqual(goals['pickup'],['pickup #102 Shell 4.6m'])
        self.assertEqual(goals['use_switch'],['use_switch #805 Lift 2.5m; upper route keys: blue','use_switch #662 Door switch 42.0m'])
        variants=[change_goal(row,None),change_goal(row,goals['pickup'][0]),change_goal(row,goals['use_switch'][0])]
        self.assertEqual(row,original)
        for variant in variants:
            self.assertEqual(variant['label'],'pickup')
            self.assertEqual(variant['question'],row['question'])
            self.assertNotIn('Previous command result:',variant['state'])
            world='\n'.join(l for l in variant['state'].splitlines() if not l.startswith('Current command:'))
            self.assertEqual(world,variants[0]['state'])
        row['question']['criteria'].pop('pickup')
        self.assertNotIn('pickup',goal_headers(row))
        row['question']['criteria']['continue']='Continue.'
        with self.assertRaisesRegex(ValueError,'Explicit'):goal_headers(row)

    def test_offline_resupply_labels_include_owned_shotguns_with_low_shells(self):
        from training.map2_teacher import labels
        s=json.loads((Path(__file__).parent/'fixtures/authority-state.json').read_text())
        s.update(hp=100,armor=100,enemies=[],door=None,switches=[],keys=[])
        for slot,entry in s['inventory'].items():
            entry.update(owned=int(slot in ('1','2','3')),ammo=50 if slot in ('2','4') else 0)
        item=dict(id=77,name='Shotgun',category='Weapon',x=64.,y=0.,z=0.,distance=2.,bearing=0.,reachable=True)
        geometry=SimpleNamespace(nearest=lambda point:point)
        def choice(enabled):
            packet=request(s,{77:item},None)
            return labels(packet,s,{(64.,0.)},geometry,weapon_resupply=enabled)['command']
        self.assertEqual(choice(True),'collect_77')
        self.assertEqual(choice(False),'explore')
        s['inventory']['3']['ammo']=20
        self.assertEqual(choice(True),'explore')
        s['inventory']['3']['ammo']=0;item['distance']=21.
        self.assertEqual(choice(True),'explore')

    def test_combat_labels_use_visible_targets_and_are_available_for_all_actions(self):
        packet,item=self.packet()
        enemies=[c['target'] for c in packet['commands'].values() if c['action']=='attack']
        self.assertTrue(enemies)
        for command in packet['commands'].values():
            if command['action']=='attack':command['target']['visible']=False
        gold=dict(command='wait',weapon='pistol')
        rows={r['kind']:r for r in examples(packet,gold,'test',0,0,explicit_actions=True,pickup_combat=True)}
        self.assertEqual(rows['combat']['label'],'hold')
        self.assertEqual(set(rows['combat']['question']['criteria']),{'hold'})
        target=next(c['target'] for c in packet['commands'].values() if c['action']=='attack')
        for command in packet['commands'].values():
            if command['action']=='attack' and command['target']['id']==target['id']:command['target']['visible']=True
        rows={r['kind']:r for r in examples(packet,gold,'test',0,0,explicit_actions=True,pickup_combat=True)}
        self.assertEqual(rows['combat']['label'],str(target['id']))
        self.assertEqual(rows['command']['label'],'wait')


if __name__=='__main__':unittest.main()
