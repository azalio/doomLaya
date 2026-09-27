import math,random,unittest
from training.sampling import epoch_rows,parse_weights,selection_score


class SamplingTest(unittest.TestCase):
    def test_default_epoch_keeps_each_example_once(self):
        rows=[{'category':str(i)} for i in range(30)]
        result=epoch_rows(rows,{},random.Random(8))
        self.assertCountEqual(result,rows)
        self.assertEqual(rows,[{'category':str(i)} for i in range(30)])

    def test_rare_required_behavior_affects_sampling_and_selection(self):
        rows=[{'kind':'command','category':'route'} for _ in range(99)]+[{'kind':'command','category':'look'}]
        weighted=epoch_rows(rows,{'look':99},random.Random(771))
        self.assertGreater(sum(r['category']=='look' for r in weighted),30)
        failure=[(r,r['category']!='look') for r in rows]
        self.assertAlmostEqual(selection_score(failure,{},{}),.99)
        self.assertAlmostEqual(selection_score(failure,{'look':99},{}),.5)
        self.assertEqual(selection_score([(r,True) for r in rows],{'look':99},{}),1)

    def test_invalid_and_duplicate_weights_are_rejected(self):
        for specs in (['x=0'],['x=nan'],['x=inf'],['x=-1'],['x=2','x=3'],['x']):
            with self.subTest(specs=specs),self.assertRaises(ValueError):parse_weights(specs)
