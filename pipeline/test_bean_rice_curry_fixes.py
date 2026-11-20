import unittest,json
from pathlib import Path
from auto_match import auto_match
from build_month import classify_main_weight,classify_side_weight,expand_main,expand_side,build_item
from exchange_unit import compute_exchange_units

class BeanRiceCurryFixTest(unittest.TestCase):
    def test_beef_rice_spelling_uses_same_volume_serving(self):
        matched = auto_match('쇠고기콩나물밥')
        cache = {'쇠고기콩나물밥': matched}
        self.assertEqual(matched['code'], 'D701-047280000-0001')
        self.assertEqual(matched['unit'], 'ml')
        parts = expand_main('쇠고기콩나물밥&양념장', '401', '중식 - Korean Dining', cache)
        self.assertEqual([(n, w) for n, w, _ in parts], [('쇠고기콩나물밥', 417), ('양념장', 9)])
        name, amount, note = parts[0]
        self.assertIn('417mL', note)
        self.assertAlmostEqual(build_item(name, amount, note, cache)['contrib']['kcal'], 546.27)

    def test_long_soybean_soup_name_uses_soup_not_side_serving(self):
        for unit, expected in [('g', 283), ('ml', 272)]:
            cache = {'건새우시금치된장국': {'unit': unit}}
            self.assertEqual(classify_main_weight('건새우시금치된장국', cache)[0], expected)
            self.assertEqual(classify_side_weight('건새우시금치된장국', cache)[0], expected)

    def test_complete_beef_rice_database_and_units(self):
        m=auto_match('소고기콩나물밥')
        self.assertEqual(m['code'],'D701-047280000-0001')
        self.assertEqual(m['unit'],'ml')
        w,_=classify_main_weight('소고기콩나물밥',{'소고기콩나물밥':m})
        self.assertEqual(w,417)
        self.assertAlmostEqual(build_item('소고기콩나물밥',w,'',{'소고기콩나물밥':m})['contrib']['kcal'],546.27)

    def test_cooked_exchange_reference_not_raw_ingredient_sum(self):
        recipe=next(r for r in json.loads((Path(__file__).resolve().parent.parent/'custom_exchange_recipes.json').read_text(encoding='utf-8')) if r['name']=='소고기콩나물밥')
        self.assertAlmostEqual(sum(i['weight_g'] for i in recipe['ingredients']),recipe['weight_g'])
        self.assertEqual(recipe['ingredients'][0]['food_name'],'멥쌀, 백미, 밥')
        self.assertEqual(recipe['ingredients'][0]['weight_g'],180)
        full=compute_exchange_units('소고기콩나물밥',417,use_plaza_servings=True)
        half=compute_exchange_units('소고기콩나물밥',208.5,use_plaza_servings=True)
        self.assertTrue(full['matched'])
        self.assertEqual(full['unresolved_ingredients'],[])
        self.assertLess(full['units']['곡류군'],7)
        self.assertGreater(full['units']['어육류군'],0)
        for group in full['units']:self.assertAlmostEqual(full['units'][group],half['units'][group]*2)

    def test_side_portions_are_not_sauce_or_generic_side(self):
        self.assertEqual(expand_side('간장마늘쫑')[0][1],25)
        self.assertEqual(expand_side('감자모닝빵')[0][1],30)

if __name__=='__main__':unittest.main()
