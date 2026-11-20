from pathlib import Path
import json,unittest
ROOT=Path(__file__).resolve().parent.parent
class FridayMenus(unittest.TestCase):
    def test_fish_cutlet_reuses_existing_same_corner_set(self):
        rows=json.loads((ROOT/'web/site_data.json').read_text(encoding='utf-8'))
        current=next(r for r in rows if r['date']=='2026-11-20' and r['shop']=='105' and r['category']=='양식')
        previous=next(r for r in rows if r['date']=='2026-11-06' and r['shop']=='105' and r['main']=='생선까스')
        self.assertEqual(current['components'],previous['components'])
        self.assertEqual(current['components'],['생선까스','쌀밥','샐러드','김치','우동국'])
    def test_confirmed_sides_once_and_broth_uses_approved_basis(self):
        rows=json.loads((ROOT/'web/site_data.json').read_text(encoding='utf-8'))
        for main in ['추어탕','꼬막비빔밥']:
            row=next(r for r in rows if r['date']=='2026-11-20' and r['shop']=='105' and r['main']==main)
            for name in ['만두','김치','오그락지','우동국']:self.assertEqual(row['components'].count(name),1)
            self.assertNotIn('장국',row['components'])
            broth=next(i for i in row['itemDetails'] if i['display']=='우동국')
            self.assertEqual(broth['weight_g'],120)
            self.assertEqual(broth['calculationName'],'우동국')
            self.assertEqual(row['unmatched'],[])
            self.assertEqual(row['exchangeUnits']['unmatched'],[])
            self.assertAlmostEqual(row['kcal'],sum(i['contrib'].get('kcal',0) for i in row['itemDetails']),delta=0.051)
            self.assertEqual(row['components'].count('쌀밥'),1 if main=='추어탕' else 0)
    def test_user_served_dishes_are_distinct_from_nutrition_substitution(self):
        meals=json.loads((ROOT/'pipeline/hyu_allergy_incremental/meal_estimates.json').read_text(encoding='utf-8'))
        for main in ['추어탕','꼬막비빔밥']:
            meal=next(m for m in meals if m['meal_key'][0]=='2026-11-20' and m['meal_key'][1]=='105' and m['meal_key'][3]==main)
            parts=[c for c in meal['components'] if c.get('userReviewNotes',{}).get('evidenceType')=='user_confirmed_served_component']
            self.assertEqual({p['name'] for p in parts},{'만두','김치','오그락지','장국'})
            self.assertNotIn('우동국',[c['name'] for c in meal['components']])
            self.assertTrue(all(not p['userReviewNotes']['actualIngredientsVerified'] for p in parts))
if __name__=='__main__':unittest.main()
