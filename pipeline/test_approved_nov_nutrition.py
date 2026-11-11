import copy,hashlib,json,subprocess,unittest
from pathlib import Path
from approved_nov_nutrition import TARGETS,recipe_match,apply_approved_nutrition
from build_month import NUT_FIELDS,DV,BENEFICIAL,DISQUALIFYING,compute_tray,load_cache
from apply_nov_nutrition import ROOT,key

class ApprovedNutritionTests(unittest.TestCase):
 def test_five_complete_matches_and_recipe_mass(self):
  rows=json.loads((ROOT/'web/site_data.json').read_text(encoding='utf-8'))
  found=[]
  for row in rows:
   for item in row['itemDetails']:
    alias=TARGETS.get((row['date'],str(row['shop']),item['display']))
    if not alias: continue
    found.append(alias)
    self.assertTrue(item['matched']);self.assertNotIn(item['display'],row['unmatched'])
    self.assertEqual(item['source'],'recipe_decompose')
    self.assertGreater(item['contrib']['kcal'],0)
    self.assertTrue(item['missing']) # Incomplete labels must remain incomplete.
    for field in NUT_FIELDS:
     expected=sum((g['per100'][field] or 0)*g['weight_g']/100 for g in item['nutritionIngredients'])
     self.assertAlmostEqual(item['contrib'][field],expected)
  self.assertEqual(len(found),5)
 def test_fixed_recipe_choices(self):
  matches={k[2]:recipe_match(v) for k,v in TARGETS.items()}
  self.assertFalse(any('소고기' in i['name'] for i in matches['온모밀']['nutrition_ingredients']))
  self.assertFalse(any('닭고기' in i['name'] for i in matches['불닭크림우동']['nutrition_ingredients']))
  fries=matches['치즈맛감자']['nutrition_ingredients']
  self.assertEqual([i['weight_g'] for i in fries],[67.2,5])
  self.assertAlmostEqual(fries[1]['per100']['kcal']*.05,20)
  shrimp=matches['새우튀김덮밥']['nutrition_ingredients']
  self.assertEqual([i['weight_g'] for i in shrimp],[250,150,18])
  self.assertNotIn('콩기름',[i['name'] for i in shrimp])
 def test_tray_totals_nrf_and_snapshot(self):
  rows=json.loads((ROOT/'web/site_data.json').read_text(encoding='utf-8'))
  for r in rows:
   if not any(i.get('nutritionRecipe') for i in r['itemDetails']):continue
   totals={f:sum(i['contrib'][f] for i in r['itemDetails']) for f in NUT_FIELDS}
   for f in NUT_FIELDS:self.assertEqual(r[f],round(totals[f],2 if f in ('fe','satFat') else 1))
   scale=100/totals['kcal']
   ben=sum(min(totals[f]*scale/dv,1)*100 for f,dv in zip(['protein','fiber','ca','fe','vitA','vitC'],[50,28,1300,18,900,90]))
   dis=sum(min(totals[f]*scale/dv,1)*100 for f,dv in zip(['satFat','sugar','na'],[20,125,2300]))
   self.assertEqual(r['nrf'],round(ben-dis,1))
  snap=json.loads((ROOT/'web/menu_exchange_snapshot.json').read_text(encoding='utf-8'))
  self.assertEqual(snap['sourceSha256'],hashlib.sha256((ROOT/'web/site_data.json').read_bytes()).hexdigest())
  self.assertEqual((ROOT/'site_data.json').read_bytes(),(ROOT/'web/site_data.json').read_bytes())
 def test_scope_and_team_data_preserved(self):
  old=json.loads(subprocess.check_output(['git','show','911b66d:web/site_data.json'],cwd=ROOT))
  new=json.loads((ROOT/'web/site_data.json').read_text(encoding='utf-8'))
  self.assertEqual(len(old),len(new)); changed=0
  for a,b in zip(old,new):
   self.assertEqual(key(a),key(b));self.assertEqual(a['exchangeUnits'],b['exchangeUnits'])
   self.assertEqual(a['photo'],b['photo']);self.assertEqual(a['weight'],b['weight'])
   if a!=b:
    changed+=1
    for x,y in zip(a['itemDetails'],b['itemDetails']):
     if (a['date'],str(a['shop']),x['display']) not in TARGETS:self.assertEqual(x,y)
   else:self.assertEqual(a,b)
  self.assertEqual(changed,3)
 def test_future_pipeline_and_idempotence(self):
  lunches=json.loads((ROOT/'pipeline/month_lunch_parsed.json').read_text(encoding='utf-8'))
  cache=load_cache();count=0
  for lunch in lunches:
   if str(lunch['shop'])!='204' or lunch['date'] not in {x[0] for x in TARGETS}:continue
   tray=compute_tray(lunch,cache)
   for i in tray['item_detail']:
    if (lunch['date'],'204',i['display']) in TARGETS:
     self.assertTrue(i['matched']);count+=1
   original=copy.deepcopy(tray['item_detail']);apply_approved_nutrition(tray['item_detail'],lunch)
   self.assertEqual(original,tray['item_detail'])
  self.assertEqual(count,5)

if __name__=='__main__':unittest.main()
