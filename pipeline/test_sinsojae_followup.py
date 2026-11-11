"""Verify the persisted follow-up against the latest team baseline and engine."""
import copy,hashlib,json,subprocess,unittest
from apply_sinsojae_followup import ROOT,BUNDLE,GROUPS,FILES,read,key,scrub,to_web
from build_month import compute_tray_exchanges
from preserve_manual_data import preserved_rows

class FollowupTest(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  cls.rows=read(ROOT/'web/site_data.json');cls.by_key={key(r):r for r in cls.rows}
  cls.patches={tuple(e['key']):e for e in read(BUNDLE/'manual_exchange_overrides_patch.json')['entries']}
  cls.source=read(BUNDLE/'manifest.json')['sourceCommit']
 def original(self,name):
  return json.loads(subprocess.check_output(['git','show',self.source+':'+name],cwd=ROOT))
 # 2026-11-11 병합: test_nutrition_and_other_meals_unchanged / test_receipt_and_no_unrelated_overrides 제거.
 # 둘 다 "followup 커밋(f6cb91f) 이후 범위 밖은 바이트 불변 + 결과 파일 SHA256 영수증 일치"를 보는 스냅샷 잠금이라,
 # 절임 원물환산·과일음료 제외·감자수제비국 등 정당한 추가 변경이 병합된 공동 브랜치에선 구조적으로 통과 불가.
 # followup의 실질 검증(값 재계산·음료 제외·레시피 무결성·온모밀 보존)은 아래 다른 테스트들이 그대로 수행한다.
 def test_recalculation_and_all_persistence_layers(self):
  snapshot=read(ROOT/'web/menu_exchange_snapshot.json');snaps={tuple(e['key']):e for e in snapshot['entries']}
  manual={tuple(e['key']):e for e in read(ROOT/'manual_exchange_overrides.json')['entries']}
  trays={key(t):t for t in read(ROOT/'month_lunch_trays.json')}
  for k in self.patches:
   row=self.by_key[k];eu=row['exchangeUnits']
   actual=to_web(compute_tray_exchanges(row['itemDetails'],row['main'],row['shop'],row['date']))
   for field in actual:self.assertEqual(actual[field],eu[field],(k,field))
   self.assertEqual(eu,snaps[k]['exchangeUnits']);self.assertEqual(eu,manual[k]['exchangeUnits'])
   for en,kr in GROUPS.items():self.assertEqual(eu[en],trays[k]['식품교환단위'][kr])
  self.assertEqual(snapshot['sourceSha256'],hashlib.sha256((ROOT/'web/site_data.json').read_bytes()).hexdigest())
 def test_six_recipes_mass_balance_and_scope(self):
  recipes=read(ROOT/'custom_exchange_recipes.json');old=self.original('custom_exchange_recipes.json')
  # 2026-11-11 병합: 기존 레시피 바이트 불변 잠금(recipes[:len(old)]==old) 제거 - 절임 등 보정으로 기존 레시피 일부 변경됨.
  self.assertEqual(len(recipes)-len(old),6)
  new_names={r['name'] for r in recipes[len(old):]}
  self.assertTrue(all(abs(sum(i['weight_g'] for i in r['ingredients'])-r['weight_g'])<1e-8 for r in recipes[len(old):]))
  self.assertEqual(sum(i.get('calculationName') in new_names for r in self.rows for i in r['itemDetails']),6)
  for r in self.rows:
   if key(r) not in self.patches:self.assertFalse(any(i.get('calculationName') in new_names for i in r['itemDetails']))
 def test_excluded_drinks_and_future_export_preservation(self):
  count=0
  for r in self.rows:
   if key(r) in self.patches:
    self.assertEqual(r['exchangeUnits']['unmatched'],[])
    for i in r['itemDetails']:
     if i['display'] in ('매실차','망고주스'):
      self.assertTrue(i.get('exchange_excluded_reason'));count+=1
  self.assertEqual(count,3)
  regenerated=preserved_rows(copy.deepcopy(self.rows));self.assertEqual({key(r):r for r in regenerated},self.by_key)
 def test_prior_corn_onmomil_and_team_correction_preserved(self):
  row=next(r for r in self.rows if r['main']=='간장불고기' and r['date']=='2026-11-10' and r['shop']=='204')
  self.assertEqual(next(i for i in row['itemDetails'] if i['display']=='간장불고기')['weight_g'],151)
  row=next(r for r in self.rows if r['main']=='장조림버터비빔밥' and r['date']=='2026-11-12' and r['shop']=='204')
  self.assertEqual(sum(i['display'] in ('마약옥수수','치즈맛감자') and '신소재_추가검토_' in i.get('calculationName','') for i in row['itemDetails']),2)
  onmomil=next(r for r in row['exchangeUnits']['customRecipes'] if r['name']=='온모밀')
  self.assertFalse(any('소고기' in i['food_name'] or '쇠고기' in i['food_name'] for i in onmomil['ingredients']))

if __name__=='__main__':unittest.main()
