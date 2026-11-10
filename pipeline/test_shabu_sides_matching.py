import unittest,json
from pathlib import Path
from auto_match import auto_match
from build_month import expand_main,build_item,compute_tray_exchanges
from exchange_unit import compute_exchange_units
ROOT=Path(__file__).resolve().parent.parent

class ShabuSidesMatchingTest(unittest.TestCase):
    def test_chili_is_sauce_not_half_noodle_bowl(self):
        parts=expand_main('채선당샤브국수&칠리S',shop='401')
        self.assertEqual([(n,w) for n,w,_ in parts],[('소고기샤브샤브',297),('칼국수면',200),('칠리S',9)])
        match=auto_match('칠리S')
        self.assertEqual(match['name'],'칠리소스(소포장)')
        item=build_item('칠리S',9,'',{'칠리S':match})
        self.assertAlmostEqual(item['contrib']['kcal'],13.95)
        result=compute_tray_exchanges([item],'채선당샤브국수&칠리S','401','2026-11-09')
        self.assertNotIn('칠리S',result['미매칭_항목'])
        self.assertTrue(any('칠리S' in note and '제외' in note for note in result['recipeNotes']))

    def test_shabu_noodle_nutrition_includes_each_part_once(self):
        shabu=auto_match('소고기샤브샤브');noodle=auto_match('칼국수면')
        self.assertEqual(shabu['code'],'D306-287180000-0001')
        self.assertEqual(noodle['name'],'칼국수면, 생것, 삶은것')
        cache={'소고기샤브샤브':shabu,'칼국수면':noodle}
        parts=expand_main('채선당샤브국수',shop='401',cache=cache)
        self.assertEqual(sum(w for _,w,_ in parts),497)
        items=[build_item(n,w,note,cache) for n,w,note in parts]
        self.assertTrue(all(i['matched'] for i in items))
        self.assertAlmostEqual(sum(i['contrib']['kcal'] for i in items),410.68)

    def test_shabu_exchange_recipe_has_explicit_broth_and_cooked_noodles(self):
        recipes={r['name']:r for r in json.loads((ROOT/'custom_exchange_recipes.json').read_text(encoding='utf-8'))}
        shabu=recipes['소고기샤브샤브']
        self.assertAlmostEqual(sum(i['weight_g'] for i in shabu['ingredients']),297)
        self.assertAlmostEqual(next(i['weight_g'] for i in shabu['ingredients'] if i['food_name']=='물'),149.8)
        for n,w in [('소고기샤브샤브',297),('칼국수면',200)]:
            full=compute_exchange_units(n,w,False);half=compute_exchange_units(n,w/2,False)
            self.assertTrue(full['matched']);self.assertEqual(full['unresolved_ingredients'],[])
            for group in full['units']:self.assertAlmostEqual(full['units'][group],half['units'][group]*2)
        self.assertLess(compute_exchange_units('칼국수면',200,False)['units']['곡류군'],4)

    def test_pancake_replaces_tuna_with_squid_and_scales(self):
        recipe=next(r for r in json.loads((ROOT/'custom_exchange_recipes.json').read_text(encoding='utf-8')) if r['name']=='오징어김치전')
        self.assertEqual(recipe['weight_g'],258)
        self.assertFalse(any('다랑어' in i['food_name'] for i in recipe['ingredients']))
        self.assertEqual(next(i['weight_g'] for i in recipe['ingredients'] if i['food_name']=='오징어, 생것'),30)
        full=compute_exchange_units('오징어김치전',70,False);half=compute_exchange_units('오징어김치전',35,False)
        self.assertTrue(full['matched']);self.assertEqual(full['unresolved_ingredients'],[])
        for g in full['units']:self.assertAlmostEqual(full['units'][g],half['units'][g]*2)

    def test_sweet_potato_recipe_is_scaled_to_side_portion(self):
        recipe=next(r for r in json.loads((ROOT/'external_exchange_recipes.json').read_text(encoding='utf-8')) if r['name']=='고구마샐러드')
        self.assertTrue(recipe['source_url'].endswith('/6836476'))
        self.assertEqual(sum(i['weight_g'] for i in recipe['ingredients']),667.5)
        full=compute_exchange_units('고구마샐러드',71,False);half=compute_exchange_units('고구마샐러드',35.5,False)
        self.assertTrue(full['matched']);self.assertGreater(full['units']['지방군'],0)
        for g in full['units']:self.assertAlmostEqual(full['units'][g],half['units'][g]*2)
        self.assertEqual(auto_match('고구마샐러드')['source'],'gagong_db')

if __name__=='__main__':unittest.main()
