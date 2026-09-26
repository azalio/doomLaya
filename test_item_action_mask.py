"""Physical item feasibility never becomes a utility or target-selection policy."""
import copy
import unittest
from decision_questions import factorize,with_commitment,mask_unreachable_items,dependencies
from policy import request
import test_authority as authority


class ItemActionMaskTest(unittest.TestCase):
    def packet(self,reachable=True):
        _,s=authority.AuthorityTest().setup_state();s['hp']=100
        first=dict(s['items'][0],reachable=False)
        second=dict(first,id=999,name='Medikit',category='Health',reachable=reachable)
        s['execution']=dict(action='pickup',target_id=first['id'],status='executing',movement=None)
        packet=with_commitment(factorize(request(s,{first['id']:first,second['id']:second},authority.Exit())))
        return packet,first,second

    def test_mask_keeps_full_health_pickup_and_all_other_choices(self):
        packet,first,second=self.packet();before=copy.deepcopy(packet)
        mask_unreachable_items(packet)
        self.assertEqual(set(packet['targets']['item']),{str(second['id'])})
        self.assertEqual(set(packet['questions']['item']['criteria']),{str(second['id'])})
        self.assertIn('pickup',packet['commands'])
        self.assertNotIn('continue',packet['commands'])
        self.assertNotIn('continue',packet['questions']['command']['criteria'])
        self.assertEqual(packet['questions']['weapon'],before['questions']['weapon'])
        self.assertEqual(packet['state'],before['state'])
        self.assertEqual(packet['observation'],before['observation'])
        self.assertEqual(packet['masked_unreachable_items'],[first])
        self.assertEqual(set(packet['commands']),set(before['commands'])-{'continue'})

    def test_no_item_command_remains_when_all_routes_are_impossible(self):
        packet,_,_=self.packet(False)
        mask_unreachable_items(packet)
        self.assertNotIn('pickup',packet['commands'])
        self.assertNotIn('pickup',packet['questions']['command']['criteria'])
        self.assertNotIn('item',packet['questions'])
        self.assertNotIn('item',packet['targets'])
        self.assertTrue({'exit','explore','wait'}<=set(packet['commands']))
        self.assertTrue(all('item' not in names for names in dependencies(packet).values()))

    def test_fresh_geometry_can_restore_a_previously_masked_item(self):
        packet,first,_=self.packet(False);mask_unreachable_items(packet)
        packet,first,_=self.packet(False)
        packet['targets']['item'][str(first['id'])]['reachable']=True
        mask_unreachable_items(packet)
        self.assertIn(str(first['id']),packet['questions']['item']['criteria'])
        self.assertIn('continue',packet['commands'])

    def test_missing_reachability_is_rejected_instead_of_assumed(self):
        packet,first,_=self.packet();del packet['targets']['item'][str(first['id'])]['reachable']
        with self.assertRaises(ValueError):mask_unreachable_items(packet)


if __name__=='__main__':unittest.main()
