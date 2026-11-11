"""Regression checks for the approved, date-scoped runtime application."""
import copy
import hashlib
import unittest
from apply_sinsojae_nov_matching import ROOT, BUNDLE, GROUPS, read, key
from build_month import compute_tray_exchanges
from exchange_unit import compute_exchange_units

class SinsojaeMatchingTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.rows={key(r):r for r in read(ROOT/'web/site_data.json')}
        cls.baselines=read(BUNDLE/'baseline_rows.json')
        cls.changes=read(BUNDLE/'변경내역.json')['changes']

    def test_display_and_unreviewed_nutrition_unchanged(self):
        # Later user-approved calorie reviews supersede only these baseline items.
        reviewed = {
            ('2026-11-10','참치마요덮밥'): {'참치마요덮밥'},
            ('2026-11-10','간장불고기'): {'간장불고기','베이컨감자채전'},
            ('2026-11-11','왕돈까스'): {'비엔나강정'},
            ('2026-11-12','닭볶음탕'): {'계란파국'},
            ('2026-11-13','차돌순두부찌개'): {'맛살마늘쫑볶음','알새우칩'},
        }
        derived = ('weight','kcal','protein','fat','carb','sugar','fiber','ca','fe','vitA','vitC',
                   'satFat','na','nrf','confidence','unmatched','gagongSourced','matchedDb',
                   'missingFields','qualityFlags','nutritionNotes')
        for baseline in self.baselines:
            row=copy.deepcopy(self.rows[key(baseline)])
            allowed = reviewed.get((row['date'],row['main']), set())
            if allowed:
                for field in derived:
                    if field in baseline: row[field]=baseline[field]
                    else: row.pop(field,None)
            row['exchangeUnits']=baseline['exchangeUnits']
            for old,new in zip(baseline['itemDetails'],row['itemDetails']):
                if old['display'] in allowed:
                    new.clear(); new.update(copy.deepcopy(old))
                for f in ('calculationName','exchange_weight_g','exchange_weight_note'):
                    if f in old: new[f]=old[f]
                    else: new.pop(f,None)
            self.assertEqual(row,baseline)

    def test_reviewed_calories_and_portions(self):
        expected = {('2026-11-10','참치마요덮밥'):1047.2,
                    ('2026-11-10','간장불고기'):841.8,
                    ('2026-11-11','왕돈까스'):838.0,
                    ('2026-11-12','닭볶음탕'):989.0,
                    ('2026-11-13','차돌순두부찌개'):967.0}
        for (day,main),kcal in expected.items():
            row=next(r for k,r in self.rows.items() if k[0]==day and k[1]=='204' and k[3]==main)
            self.assertEqual(row['kcal'],kcal)
            self.assertAlmostEqual(sum(i['contrib']['kcal'] for i in row['itemDetails']),kcal,delta=.1)
            self.assertFalse(row['unmatched'])
            if main=='왕돈까스':
                self.assertEqual(next(i['weight_g'] for i in row['itemDetails'] if i['display']=='왕돈까스'),151)
            if main=='차돌순두부찌개':
                chip=next(i for i in row['itemDetails'] if i['display']=='알새우칩')
                self.assertEqual(chip['weight_g'],30)
                self.assertEqual(chip['exchange_weight_g'],30)

    def test_full_precision_recalculation_and_persistence(self):
        roots={key(r):r for r in read(ROOT/'site_data.json')}
        manual={tuple(e['key']):e for e in read(ROOT/'manual_exchange_overrides.json')['entries']}
        snaps={tuple(e['key']):e for e in read(ROOT/'web/menu_exchange_snapshot.json')['entries']}
        for k in {tuple(c['key']) for c in self.changes}:
            row=self.rows[k]; eu=row['exchangeUnits']
            actual=compute_tray_exchanges(row['itemDetails'],row['main'],row['shop'],row['date'])
            for en,kr in GROUPS.items(): self.assertEqual(eu[en],actual[kr])
            self.assertEqual(eu['unmatched'],actual['미매칭_항목'])
            self.assertEqual(row,roots[k])
            self.assertEqual(eu,manual[k]['exchangeUnits'])
            self.assertEqual(eu,snaps[k]['exchangeUnits'])
        self.assertEqual(read(ROOT/'web/menu_exchange_snapshot.json')['sourceSha256'],hashlib.sha256((ROOT/'web/site_data.json').read_bytes()).hexdigest())

    def test_approved_items_resolve_without_unresolved_ingredients(self):
        self.assertEqual(len(self.changes),16)
        for c in self.changes:
            row=self.rows[tuple(c['key'])]
            item=next(i for i in row['itemDetails'] if i['display']==c['name'])
            result=compute_exchange_units(item['calculationName'],item['exchange_weight_g'],False)
            self.assertTrue(result['matched'])
            self.assertEqual(result['unresolved_ingredients'],[])
            self.assertNotIn(c['name'],row['exchangeUnits']['unmatched'])
        targets={tuple(c['key']) for c in self.changes}
        for k,row in self.rows.items():
            if k not in targets:
                self.assertFalse(any(i.get('calculationName','').startswith('신소재_202611_검토확정_') for i in row.get('itemDetails',[])))

    def test_pending_and_beef_exclusion(self):
        pending={n for k,r in self.rows.items() if k[1]=='204' and '2026-11-09'<=k[0]<='2026-11-13' for n in r['exchangeUnits']['unmatched']}
        self.assertEqual(pending,{'불닭크림우동','매실차','국물떡볶이','간장불고기','망고주스','양파절임','마약옥수수','치즈맛감자'})
        recipes=read(ROOT/'custom_exchange_recipes.json')
        recipe=next(r for r in recipes if r['name']=='신소재_202611_검토확정_온모밀')
        self.assertFalse(any('소고기' in i['food_name'] or '쇠고기' in i['food_name'] for i in recipe['ingredients']))
        self.assertAlmostEqual(sum(i['weight_g'] for i in recipe['ingredients']),72.2)

if __name__=='__main__': unittest.main()
