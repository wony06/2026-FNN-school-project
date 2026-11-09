"""Prepared-food matching and the fern/extra-noodles regression."""

import unittest

from auto_match import auto_match

from build_month import build_item, classify_side_weight, expand_side



class PreparedNutritionTest(unittest.TestCase):

    def test_fern_is_not_extra_noodles(self):

        cache = {'고사리나물': auto_match('고사리나물')}

        self.assertEqual(expand_side('고사리나물', cache=cache)[0][1], 70)

        self.assertEqual(expand_side('사리'), [])

        self.assertEqual(expand_side('우동사리'), [])



    def test_liquid_tea_not_powder(self):

        for name in ['매실차', '레몬홍차']:

            matched = auto_match(name)

            self.assertEqual(matched['per100']['kcal'], 35)

            self.assertEqual(matched['basis'], '100ml')

            self.assertFalse(matched['is_concentrate'])

            item = build_item(name, 200, '', {name:matched})

            self.assertEqual(item['contrib']['kcal'], 70)

            self.assertIn('fiber', item['missing'])  # missing data stays missing



    def test_ready_soup_and_cooked_noodles(self):

        for name, expected in [('크림스프', 43.32), ('감자수제비국', 239.36), ('유부우동국', 46.24)]:

            matched = auto_match(name)

            weight, _ = classify_side_weight(name, {name:matched})

            item = build_item(name, weight, '', {name:matched})

            self.assertAlmostEqual(item['contrib']['kcal'], expected)

            self.assertIn('미확인', item['weight_note'])



    def test_dakgangjeong_nutrition_uses_displayed_grams(self):
        matched = auto_match('닭강정')
        item = build_item('닭강정', 72.2, '', {'닭강정':matched})
        self.assertEqual(matched['total_parsed_weight_g'], 300)
        self.assertAlmostEqual(item['contrib']['kcal'], 160.668826)
        self.assertEqual(item['weight_g'], 72.2)
        double = build_item('닭강정', 144.4, '', {'닭강정':matched})
        self.assertAlmostEqual(double['contrib']['kcal'], item['contrib']['kcal'] * 2)

    def test_pork_noodles_include_broth_weight(self):

        matched = auto_match('제주고기국수')

        item = build_item('제주고기국수', 690, '', {'제주고기국수':matched})

        self.assertEqual(matched['source'], 'recipe_decompose')

        self.assertEqual(matched['recipe_batch_g'], 1222.5)

        self.assertAlmostEqual(item['contrib']['kcal'], 481.0047852760736)

        # Salt in the existing recipe is retained; this is not a zero-sodium proxy.

        self.assertGreater(item['contrib']['na'], 3000)

        self.assertIn('육수 영양정보가 없어', matched['nutrition_note'])



if __name__ == '__main__':

    unittest.main()

