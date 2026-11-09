"""Separate rice/pork must not be included in the soup component again."""
import json
import unittest
from pathlib import Path
from auto_match import auto_match
from build_month import build_item, DECOMPOSE_OVERRIDES
from exchange_unit import compute_exchange_units

ROOT = Path(__file__).resolve().parent.parent
NAME = '수육국밥국물(밥·고기 제외)'

class GukbapDedupTest(unittest.TestCase):
    def test_components_do_not_reuse_whole_gukbap(self):
        parts = DECOMPOSE_OVERRIDES['얼큰수육국밥']
        self.assertEqual([(p[0], p[1]) for p in parts], [(NAME,197), ('돼지고기수육',86)])

    def test_recipe_excludes_rice_and_meat_and_keeps_dilution(self):
        recipe = next(r for r in json.loads((ROOT/'custom_exchange_recipes.json').read_text(encoding='utf-8')) if r['name']==NAME)
        self.assertEqual(recipe['weight_g'],757)
        self.assertEqual(sum(i['weight_g'] for i in recipe['ingredients']),57)
        self.assertFalse(any(i['food_group'] in ('곡류 및 그 제품','육류') for i in recipe['ingredients']))
        result = compute_exchange_units(NAME,197,use_plaza_servings=False)
        self.assertTrue(result['matched'])
        self.assertEqual(result['units']['곡류군'],0)
        self.assertEqual(result['units']['어육류군'],0)
        self.assertGreater(result['units']['채소군'],0)
        double = compute_exchange_units(NAME,394,use_plaza_servings=False)
        self.assertAlmostEqual(double['units']['채소군'],result['units']['채소군']*2)

    def test_nutrition_uses_same_recipe_and_marks_unknown_broth(self):
        matched = auto_match(NAME)
        item = build_item(NAME,197,'',{NAME:matched})
        self.assertEqual(matched['recipe_batch_g'],757)
        self.assertLess(item['contrib']['kcal'],10)
        self.assertIn('na',item['missing'])
        self.assertIn('실제 육수 성분',item['weight_note'])

if __name__=='__main__': unittest.main()
