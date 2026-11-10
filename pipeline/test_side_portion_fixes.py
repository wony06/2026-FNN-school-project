import unittest,json
from pathlib import Path
from auto_match import auto_match
from build_month import classify_main_weight,classify_side_weight,expand_side,expand_main,build_item,classify_shop_side_weight,MAIN_FALLBACK
from unittest.mock import patch
from exchange_unit import compute_exchange_units

class SidePortionFixTest(unittest.TestCase):
    def test_role_separates_cutlet_portions(self):
        for name in ['생선까스','돈가스','통살치킨까스']:
            self.assertEqual(classify_main_weight(name)[0],151)
            self.assertEqual(classify_side_weight(name)[0],72.2)

    def test_shinsojae_side_policy_uses_categories_and_keeps_main(self):
        for name, expected in [('생선까스',72.2),('제육볶음',80),('감자조림',44),('숙주나물',70),('샐러드',71),('미니우동',120)]:
            with self.subTest(name=name):
                parts=expand_side(name,shop='204')
                self.assertEqual(parts[0][1],expected)
                self.assertIn('신소재 곁들임 규칙',parts[0][2])
        self.assertEqual(expand_main('생선까스',shop='204')[0][1],151)
        self.assertEqual([w for _,w,_ in expand_side('생선까스*타르소스',shop='204')],[72.2,9])

    def test_shinsojae_explicit_weights_take_precedence(self):
        # Existing manually decomposed side serving must not be overwritten by a generic fallback.
        parts=expand_side('청양마요미트볼',shop='204')
        self.assertEqual([(n,w) for n,w,_ in parts],[('미트볼',86),('청양마요',9)])

    def test_shinsojae_cannot_inherit_generic_main_fallback(self):
        # Protect the policy if a future classifier change accidentally returns a main portion.
        with patch('build_month.classify_side_weight',return_value=MAIN_FALLBACK):
            self.assertEqual(classify_shop_side_weight('새로운곁들임','204')[0],72.2)

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
