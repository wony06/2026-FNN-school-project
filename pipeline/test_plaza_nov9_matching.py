import json,unittest
from pathlib import Path
from auto_match import auto_match
from build_month import expand_main,build_item,compute_tray_exchanges,load_cache
from exchange_unit import compute_exchange_units
ROOT=Path(__file__).resolve().parent.parent

class PlazaNov9MatchingTest(unittest.TestCase):
    def test_sriracha_chicken_bowl_has_one_rice_and_fixed_total(self):
        cache=load_cache();parts=expand_main('스리라차치킨마요덮밥',shop='105',cache=cache)
        self.assertEqual(sum(w for _,w,_ in parts),418)
        weights={n:w for n,w,_ in parts}
        self.assertEqual(weights,{'쌀밥':210,'치킨까스':136,'계란지단':50,'김가루':4,'마요네즈':9,'스리라차소스':9})
        items=[build_item(n,w,note,cache) for n,w,note in parts]
        self.assertTrue(all(i['matched'] for i in items))
        self.assertAlmostEqual(sum(i['contrib']['kcal'] for i in items),935.895)
        result=compute_tray_exchanges(items,'스리라차치킨마요덮밥','105','2026-11-09')
        self.assertEqual(result['미매칭_항목'],[])
        self.assertTrue(any('스리라차소스' in n and '제외' in n for n in result['recipeNotes']))

    def test_stew_recipe_keeps_broth_in_denominator(self):
        recipe=next(r for r in json.loads((ROOT/'custom_exchange_recipes.json').read_text(encoding='utf-8')) if r['name']=='고깃집된장찌개')
        self.assertAlmostEqual(sum(i['weight_g'] for i in recipe['ingredients']),283)
        self.assertEqual(next(i['weight_g'] for i in recipe['ingredients'] if i['food_name']=='물'),203.8)
        r=compute_exchange_units('고깃집된장찌개',283,True);half=compute_exchange_units('고깃집된장찌개',141.5,True)
        self.assertTrue(r['matched']);self.assertEqual(r['unresolved_ingredients'],[])
        self.assertIn('미확인',r['recipe_note'])
        for group in r['units']:self.assertAlmostEqual(r['units'][group],half['units'][group]*2)
        self.assertEqual(auto_match('고깃집된장찌개')['source'],'gagong_db')

if __name__=='__main__':unittest.main()
