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

    def test_nutrition_and_display_unchanged(self):
        for baseline in self.baselines:
            row=copy.deepcopy(self.rows[key(baseline)])
            row['exchangeUnits']=baseline['exchangeUnits']
            for old,new in zip(baseline['itemDetails'],row['itemDetails']):
                for f in ('calculationName','exchange_weight_g','exchange_weight_note'):
                    if f in old: new[f]=old[f]
                    else: new.pop(f,None)
            self.assertEqual(row,baseline)

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
        self.assertEqual(pending,{'불닭크림우동','국물떡볶이','마약옥수수','치즈맛감자'})  # 간장불고기는 2026-11-11 중량 교정 후 적용; 양파절임은 절임 원물환산으로 매칭 해소; 매실차·망고주스는 2026-11-11 과일음료·차 교환단위 제외
        recipes=read(ROOT/'custom_exchange_recipes.json')
        recipe=next(r for r in recipes if r['name']=='신소재_202611_검토확정_온모밀')
        self.assertFalse(any('소고기' in i['food_name'] or '쇠고기' in i['food_name'] for i in recipe['ingredients']))
        self.assertAlmostEqual(sum(i['weight_g'] for i in recipe['ingredients']),72.2)

if __name__=='__main__': unittest.main()
