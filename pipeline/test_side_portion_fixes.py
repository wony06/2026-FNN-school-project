import unittest,json
from pathlib import Path
from auto_match import auto_match
from build_month import classify_main_weight,classify_side_weight,expand_side,build_item
from exchange_unit import compute_exchange_units

class SidePortionFixTest(unittest.TestCase):
    def test_role_separates_cutlet_portions(self):
        for name in ['생선까스','돈가스','통살치킨까스']:
            self.assertEqual(classify_main_weight(name)[0],151)
            self.assertEqual(classify_side_weight(name)[0],72.2)

    def test_tteokbokki_is_not_a_rice_bowl(self):
        m=auto_match('투움바떡볶이')
        self.assertEqual(classify_main_weight('투움바떡볶이',{'투움바떡볶이':m})[0],180)
        self.assertEqual(m['recipe_batch_g'],360.3)
        recipe=next(r for r in json.loads((Path(__file__).resolve().parent.parent/'custom_exchange_recipes.json').read_text(encoding='utf-8')) if r['name']=='투움바떡볶이')
        self.assertAlmostEqual(sum(i['weight_g'] for i in recipe['ingredients']),360.3)
        self.assertIn('크림',recipe['assumptions'])
        full=compute_exchange_units('투움바떡볶이',180,use_plaza_servings=False)
        half=compute_exchange_units('투움바떡볶이',90,use_plaza_servings=False)
        self.assertTrue(full['matched'])
        self.assertGreater(full['units']['우유군'],0)
        self.assertGreater(full['units']['지방군'],0)
        for group in full['units']:self.assertAlmostEqual(full['units'][group],half['units'][group]*2)
        item=build_item('투움바떡볶이',180,'',{'투움바떡볶이':m})
        doubled=build_item('투움바떡볶이',360,'',{'투움바떡볶이':m})
        self.assertAlmostEqual(doubled['contrib']['kcal'],item['contrib']['kcal']*2)
        self.assertIn('na',item['missing'])

    def test_rice_kept_and_seaweed_is_small_topping(self):
        parts=expand_side('김가루밥')
        self.assertEqual([(n,w) for n,w,_ in parts],[('쌀밥',210),('김가루',4)])

if __name__=='__main__':unittest.main()
