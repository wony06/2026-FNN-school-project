import json,unittest
from pathlib import Path
from auto_match import auto_match
from build_month import build_item,expand_main,classify_side_weight
from exchange_unit import compute_exchange_units

class GamjatangHwangtaeFixTest(unittest.TestCase):
    def test_dried_fish_portion_includes_oil_and_seasonings(self):
        root=Path(__file__).resolve().parent.parent
        recipe=next(r for r in json.loads((root/'custom_exchange_recipes.json').read_text(encoding='utf-8')) if r['name']=='쥐어채볶음')
        self.assertEqual(recipe['ingredients'][0]['weight_g'],15)
        self.assertEqual(sum(i['weight_g'] for i in recipe['ingredients']),19.5)
        self.assertEqual(classify_side_weight('쥐어채볶음')[0],19.5)
        m=auto_match('쥐어채볶음')
        item=build_item('쥐어채볶음',19.5,'',{'쥐어채볶음':m})
        self.assertEqual(m['source'],'recipe_decompose')
        self.assertGreater(item['contrib']['fat'],1.75)
        self.assertGreater(item['contrib']['sugar'],0)
        full=compute_exchange_units('쥐어채볶음',19.5,False)
        half=compute_exchange_units('쥐어채볶음',9.75,False)
        self.assertTrue(full['matched'])
        self.assertEqual(full['unresolved_ingredients'],[])
        self.assertGreater(full['units']['지방군'],0)
        for group in full['units']:self.assertAlmostEqual(full['units'][group],half['units'][group]*2)

    def test_garnishes_reduce_without_adding_rice(self):
        parts=expand_main('황태무침비빔밥')
        weights={n:w for n,w,_ in parts}
        self.assertEqual(weights['김가루'],4)
        self.assertEqual(weights['쌀밥'],220)
        self.assertAlmostEqual(sum(weights.values()),400)
        self.assertEqual(classify_side_weight('견과류멸치볶음')[0],20)

    def test_cabbage_is_raw_and_soup_has_no_noodles(self):
        cabbage=auto_match('적양배추')
        self.assertEqual(cabbage['source'],'db104_direct')
        self.assertEqual(cabbage['name'],'양배추, 적색, 생것')
        self.assertEqual(cabbage['unit'],'g')
        soup=auto_match('유부우동국')
        self.assertEqual(soup['code'],'D605-244000000-0001')
        self.assertEqual(soup['unit'],'ml')
        self.assertEqual(classify_side_weight('유부우동국',{'유부우동국':soup})[0],272)
        self.assertAlmostEqual(build_item('유부우동국',272,'',{'유부우동국':soup})['contrib']['kcal'],46.24)
        exchange=compute_exchange_units('유부우동국',272,False)
        self.assertTrue(exchange['matched'])
        self.assertEqual(exchange['matched_name'],'유부국')
        self.assertEqual(exchange['units']['곡류군'],0)

if __name__=='__main__':unittest.main()
