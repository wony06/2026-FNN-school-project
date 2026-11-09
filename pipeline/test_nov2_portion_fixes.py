import unittest,json
from pathlib import Path
from auto_match import auto_match
from build_month import expand_main,expand_side,build_item

class Nov2PortionFixTest(unittest.TestCase):
    def test_sauce_is_not_half_of_hotpot(self):
        self.assertEqual([(n,w) for n,w,_ in expand_main('닭한마리전골&양념장')],[('닭한마리전골',283),('양념장',9)])
        self.assertEqual(expand_side('탕평채')[0][1],70)
        self.assertEqual(expand_side('해물까스&타르소스')[0][1],72.2)

    def test_hotpot_uses_diluted_recipe_with_salt(self):
        m=auto_match('닭한마리전골')
        self.assertEqual(m['source'],'recipe_decompose')
        self.assertEqual(m['recipe_batch_g'],2627.5)
        item=build_item('닭한마리전골',283,'',{'닭한마리전골':m})
        self.assertGreater(item['contrib']['kcal'],100)
        self.assertLess(item['contrib']['protein'],40) # no longer treats 283g as pure chicken
        self.assertGreater(item['contrib']['na'],200) # retain recipe salt rather than assume broth zero
        self.assertIn('na',item['missing'])
        doubled=build_item('닭한마리전골',566,'',{'닭한마리전골':m})
        self.assertAlmostEqual(doubled['contrib']['kcal'],item['contrib']['kcal']*2)

if __name__=='__main__':unittest.main()
