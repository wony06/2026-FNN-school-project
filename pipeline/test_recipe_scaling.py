"""Regression checks for batch recipes mistakenly counted as whole servings."""
import copy
import json
import unittest
from pathlib import Path

from exchange_unit import _recipe_scale, compute_exchange_units

ROOT = Path(__file__).resolve().parent.parent


class BatchRecipeScalingTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.recipes = {r['name']: r for r in json.loads(
            (ROOT / 'external_exchange_recipes.json').read_text(encoding='utf-8'))}

    def test_reviewed_batch_targets(self):
        cases = [('마카로니샐러드', 170, 478.5), ('푸실리샐러드', 86, 346.1),
                 ('통살치킨까스', 150, 470.5), ('메밀전병', 150, 1443.8),
                 ('돼지고기육전', 140, 445)]
        for name, portion, batch in cases:
            with self.subTest(recipe=name):
                self.assertAlmostEqual(_recipe_scale(self.recipes[name], portion), portion / batch)

    def test_ingredient_units_follow_portion_instead_of_batch(self):
        for name in ['마카로니샐러드', '푸실리샐러드', '통살치킨까스', '메밀전병', '돼지고기육전']:
            with self.subTest(recipe=name):
                small = compute_exchange_units(name, 40, use_plaza_servings=False)
                large = compute_exchange_units(name, 80, use_plaza_servings=False)
                self.assertTrue(small['matched'] and large['matched'])
                self.assertGreater(sum(small['units'].values()), 0)
                for group, value in small['units'].items():
                    self.assertAlmostEqual(large['units'][group], value * 2)

    def test_onion_and_spring_roll_follow_displayed_serving(self):
        customs = {r['name']: r for r in json.loads(
            (ROOT / 'custom_exchange_recipes.json').read_text(encoding='utf-8'))}
        for name, recipe in [('어니언링', self.recipes['어니언링']), ('야채춘권', customs['야채춘권'])]:
            with self.subTest(recipe=name):
                self.assertAlmostEqual(_recipe_scale(recipe, 72.2), 72.2 / recipe['weight_g'])
                half = compute_exchange_units(name, 36.1, use_plaza_servings=False)
                full = compute_exchange_units(name, 72.2, use_plaza_servings=False)
                self.assertTrue(full['matched'])
                self.assertGreater(full['units']['지방군'], 0)
                for group in full['units']:
                    self.assertAlmostEqual(full['units'][group], half['units'][group] * 2)

    def test_intentional_complete_serving_is_unchanged(self):
        ramen = self.recipes['돈코츠라멘']
        self.assertEqual(_recipe_scale(ramen, 150), 1)
        self.assertEqual(_recipe_scale(ramen, 543), 1)
        customs = {r['name']: r for r in json.loads(
            (ROOT / 'custom_exchange_recipes.json').read_text(encoding='utf-8'))}
        for name, recipe in customs.items():
            if name.startswith('전복표고솥밥'):
                self.assertEqual(_recipe_scale(recipe, 150), 1)


if __name__ == '__main__':
    unittest.main()
