"""Small servings, beverage state, and false soup classification regressions."""
import unittest
from auto_match import auto_match
from build_month import classify_main_weight, classify_side_weight, expand_main, expand_side, build_item

class ServingClassificationTest(unittest.TestCase):
    def test_butter_default_and_explicit_recipe(self):
        self.assertEqual(classify_side_weight('버터')[0], 5)
        self.assertEqual(expand_side('버터')[0][1], 5)
        parts=expand_main('장조림버터비빔밥')
        self.assertEqual(next(w for name,w,note in parts if name=='버터'),10)

    def test_tangsuyuk_is_not_soup(self):
        self.assertEqual(classify_side_weight('맛초킹탕수육')[0],72.2)
        self.assertEqual(classify_main_weight('맛초킹탕수육')[0],151)
        self.assertEqual(classify_side_weight('갈비탕')[0],283)
        self.assertEqual(classify_side_weight('갈비탕',{'갈비탕':{'unit':'ml'}})[0],272)

    def test_snack_uses_reference_serving(self):
        self.assertEqual(classify_side_weight('빼빼로')[0],30)
        matched=auto_match('빼빼로')
        item=build_item('빼빼로',30,'',{'빼빼로':matched})
        self.assertLess(item['contrib']['kcal'],200)

    def test_prepared_pomegranate_and_tea_portion(self):
        matched=auto_match('석류차')
        self.assertEqual(matched['code'],'D220-719000000-0146')
        self.assertEqual(matched['unit'],'ml')
        item=build_item('석류차',200,'',{'석류차':matched})
        self.assertEqual(item['contrib']['kcal'],110)
        for name in ['석류차','매실차','레몬홍차']:
            self.assertEqual(classify_side_weight(name)[0],200)

if __name__=='__main__':
    unittest.main()
