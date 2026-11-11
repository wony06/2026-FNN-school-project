"""Read-only validator. Never applies this review bundle to runtime files."""
import copy,hashlib,json,sys
from pathlib import Path
from unittest.mock import patch
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
GROUPS={'grain':'곡류군','meat':'어육류군','veg':'채소군','fat':'지방군','dairy':'우유군','fruit':'과일군'}
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def key(r):return tuple(r[f] for f in ('date','shop','category','main'))
def calculate(root=ROOT,bundle=HERE):
 sys.path.insert(0,str(root/'pipeline'))
 import build_month as bm
 import exchange_unit as ex
 recipes={r['name']:r for r in read(bundle/'custom_exchange_recipes_patch.json')}
 patches={tuple(e['key']):e['itemOverrides'] for e in read(bundle/'item_overrides_patch.json')['entries']}
 rows={key(r):r for r in read(root/'web/site_data.json')}
 original=bm.compute_exchange_units
 def compute(name,w,*args,**kwargs):
  if name not in recipes:return original(name,w,*args,**kwargs)
  r=recipes[name];units={g:0.0 for g in ex.EXCHANGE_GROUPS}
  for i in r['ingredients']:
   record=ex.DB104_BY_NAME.get(i['food_name'])
   assert record is not None or ex.FOOD_GROUP_MAP.get(i['food_group']) is None,i
   ex._add_ingredient(units,i['food_group'],record,i['weight_g']*w/r['weight_g'])
  return {'matched':True,'units':units,'source':'custom_recipe','recipe_note':r['assumptions']}
 entries=[]
 for k,ps in patches.items():
  row=copy.deepcopy(rows[k]);by_display={p['display']:p for p in ps}
  for i in row['itemDetails']:i.update(copy.deepcopy(by_display.get(i['display'],{})))
  with patch.object(bm,'compute_exchange_units',compute):
   # Current engine consumes calculationName; originals remain for exclusions/notes.
   raw=bm.compute_tray_exchanges(row['itemDetails'],row['main'],row['shop'],row['date'])
  db=raw['매칭DB'];eu={en:raw[kr] for en,kr in GROUPS.items()}
  eu.update(unmatched=raw['미매칭_항목'],externalRecipes=raw['externalRecipes'],recipeNotes=raw['recipeNotes'],
    matchedDb={'menugen':db['menugen'],'recipeDb':db['recipe_db'],'db104':db['db104_direct']})
  customs={r['name']:copy.deepcopy(r) for r in row['exchangeUnits'].get('customRecipes',[])}
  for p in ps:
   if p.get('calculationName') in recipes:customs[p['calculationName']]=copy.deepcopy(recipes[p['calculationName']])
  eu['customRecipes']=list(customs.values())
  entries.append({'key':list(k),'exchangeUnits':eu,'itemOverrides':copy.deepcopy(ps)})
 return entries
def validate(root=ROOT,bundle=HERE):
 manifest=read(bundle/'manifest.json')
 before={f:(root/f).read_bytes() for f in manifest['protectedSourceSha256']}
 for f,d in before.items():assert hashlib.sha256(d.replace(b'\r\n',b'\n')).hexdigest()==manifest['protectedSourceSha256'][f],f+' changed; rebase review first'
 rows={key(r):r for r in read(root/'web/site_data.json')}
 baseline=read(bundle/'baseline_rows.json')
 for r in baseline:assert rows[key(r)]==r,key(r)
 recipes=read(bundle/'custom_exchange_recipes_patch.json');assert len(recipes)==6
 for r in recipes:assert abs(sum(i['weight_g'] for i in r['ingredients'])-r['weight_g'])<1e-8,r['name']
 actual=calculate(root,bundle);expected=read(bundle/'manual_exchange_overrides_patch.json')['entries']
 assert actual==expected,'full meal recalculation differs'
 assert len(actual)==6
 for entry in actual:
  assert entry['exchangeUnits']['unmatched']==[],entry['key']
  row=copy.deepcopy(rows[tuple(entry['key'])]);old=copy.deepcopy(row)
  by_display={p['display']:p for p in entry['itemOverrides']}
  for item in row['itemDetails']:
   p=by_display.get(item['display'],{})
   assert set(p)<={'display','calculationName','exchange_weight_g','exchange_weight_note','exchange_excluded_reason'}
   for f in ('weight_g','contrib','matched','source'):assert f not in p
  assert row==old
 exclusions=read(bundle/'exchange_exclusions.json')['entries'];assert len(exclusions)==3
 for exclusion in exclusions:
  entry=next(e for e in actual if e['key']==exclusion['key'])
  assert exclusion['display'] not in entry['exchangeUnits']['unmatched']
  assert any(p.get('display')==exclusion['display'] and p.get('exchange_excluded_reason') for p in entry['itemOverrides'])
 pork=next(r for r in baseline if r['main']=='간장불고기')
 assert next(i for i in pork['itemDetails'] if i['display']=='간장불고기')['weight_g']==151
 corn=next(e for e in actual if e['key'][3]=='장조림버터비빔밥')
 assert sum(p['display'] in ('마약옥수수','치즈맛감자') for p in corn['itemOverrides'])==2
 assert any('소고기' in r.get('assumptions','') and r['name']=='온모밀' for r in corn['exchangeUnits']['customRecipes'])
 for f,b in before.items():assert (root/f).read_bytes()==b,f+' mutated'
 return {'recipes':6,'meals':6,'excludedItems':3,'fullRecalculation':'passed','ingredientMassBalance':'passed',
  'latestBaselineAndNutritionPreserved':'passed','cornAndCheeseCumulative':'passed','onmomilBeefExclusionPreserved':'passed',
  'runtimeFilesUnchanged':'passed'}
if __name__=='__main__':print(json.dumps(validate(),ensure_ascii=False))
