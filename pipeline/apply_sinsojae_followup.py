"""Apply the reviewed six recipes and three exclusions without nutrient changes."""
import copy
import hashlib
import importlib.util
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent
BUNDLE=ROOT/'exchange_matching_updates/2026-11-11_sinsojae_followup'
GROUPS={'grain':'곡류군','meat':'어육류군','veg':'채소군','fat':'지방군','dairy':'우유군','fruit':'과일군'}
FILES=['custom_exchange_recipes.json','manual_exchange_overrides.json','site_data.json','month_lunch_trays.json','web/site_data.json','web/menu_exchange_snapshot.json']
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def write(p,d):
 ending='\r\n' if p.name in ('custom_exchange_recipes.json','manual_exchange_overrides.json','month_lunch_trays.json','menu_exchange_snapshot.json') else '\n'
 p.write_text(json.dumps(d,ensure_ascii=False,indent=None if p.name=='site_data.json' else 1),encoding='utf-8',newline=ending)
def key(r):return tuple(r[f] for f in ('date','shop','category','main'))
def applied_note(s):
 replacements={
  '웹사이트·GitHub·기존 영양성분 미변경, 전달용 누적':'2026-11-11 웹사이트 적용, 기존 영양성분 유지',
  '영양성분 및 웹사이트 실행 데이터 유지, 전달용 수정안으로 누적':'기존 영양성분 유지, 2026-11-11 웹사이트 반영',
  '웹사이트·GitHub 미반영':'2026-11-11 웹사이트 적용',
  '웹사이트 미반영':'2026-11-11 웹사이트 적용',
 }
 for a,b in replacements.items():s=s.replace(a,b)
 return s
def to_web(raw):
 db=raw['매칭DB']
 return {**{en:raw[kr] for en,kr in GROUPS.items()},'unmatched':raw['미매칭_항목'],
  'externalRecipes':raw['externalRecipes'],'recipeNotes':raw['recipeNotes'],
  'matchedDb':{'menugen':db['menugen'],'recipeDb':db['recipe_db'],'db104':db['db104_direct']}}
def update_row(row,entry):
 row['exchangeUnits']=copy.deepcopy(entry['exchangeUnits'])
 patches={p['display']:p for p in entry['itemOverrides']}
 for i in row['itemDetails']:i.update(copy.deepcopy(patches.get(i['display'],{})))
def scrub(row,original):
 row=copy.deepcopy(row);row['exchangeUnits']=original['exchangeUnits']
 for old,new in zip(original.get('itemDetails',[]),row.get('itemDetails',[])):
  for f in ('calculationName','exchange_weight_g','exchange_weight_note','exchange_excluded_reason'):
   if f in old:new[f]=old[f]
   else:new.pop(f,None)
 return row
def apply():
 receipt_path=BUNDLE/'applied_runtime_receipt.json'
 if receipt_path.exists():
  receipt=read(receipt_path)
  for f,digest in receipt['resultSha256'].items():
   assert hashlib.sha256((ROOT/f).read_bytes()).hexdigest()==digest,f+' changed after application'
  print('Already applied; runtime matches receipt.');return
 spec=importlib.util.spec_from_file_location('review_validator',BUNDLE/'validate_staged.py')
 validator=importlib.util.module_from_spec(spec);spec.loader.exec_module(validator)
 preflight=validator.validate(ROOT,BUNDLE)
 before={f:read(ROOT/f) for f in FILES}
 recipes=read(BUNDLE/'custom_exchange_recipes_patch.json')
 existing=copy.deepcopy(before['custom_exchange_recipes.json'])
 assert not ({r['name'] for r in existing}&{r['name'] for r in recipes})
 for r in recipes:r['assumptions']=applied_note(r['assumptions'])
 write(ROOT/'custom_exchange_recipes.json',existing+recipes)
 from build_month import compute_tray_exchanges
 entries=read(BUNDLE/'manual_exchange_overrides_patch.json')['entries']
 by_key={tuple(e['key']):e for e in entries};rows=copy.deepcopy(before['web/site_data.json'])
 for row in rows:
  if key(row) not in by_key:continue
  entry=by_key[key(row)];update_row(row,entry)
  eu=to_web(compute_tray_exchanges(row['itemDetails'],row['main'],row['shop'],row['date']))
  projected=entry['exchangeUnits']
  for g in GROUPS:assert eu[g]==projected[g],(key(row),g)
  assert eu['unmatched']==projected['unmatched']==[]
  customs={r['name']:copy.deepcopy(r) for r in row['exchangeUnits'].get('customRecipes',[])}
  for r in recipes:
   if any(i.get('calculationName')==r['name'] for i in row['itemDetails']):customs[r['name']]=copy.deepcopy(r)
  for r in customs.values():r['assumptions']=applied_note(r.get('assumptions',''))
  eu['customRecipes']=list(customs.values());row['exchangeUnits']=eu;entry['exchangeUnits']=copy.deepcopy(eu)
 row_map={key(r):r for r in rows}
 for old,new in zip(before['web/site_data.json'],rows):
  assert (scrub(new,old) if key(new) in by_key else new)==old,key(new)
 manual=copy.deepcopy(before['manual_exchange_overrides.json'])
 for entry in entries:
  saved=next((e for e in manual['entries'] if e['key']==entry['key']),None)
  if saved is None:saved={'key':entry['key']};manual['entries'].append(saved)
  saved['exchangeUnits']=copy.deepcopy(entry['exchangeUnits'])
  ps={p['display']:p for p in saved.get('itemOverrides',[])}
  for p in entry['itemOverrides']:ps.setdefault(p['display'],{'display':p['display']}).update(copy.deepcopy(p))
  saved['itemOverrides']=list(ps.values())
 write(ROOT/'manual_exchange_overrides.json',manual)
 write(ROOT/'web/site_data.json',rows)
 root_rows=copy.deepcopy(before['site_data.json'])
 for row in root_rows:
  if key(row) in by_key:update_row(row,by_key[key(row)])
 for old,new in zip(before['site_data.json'],root_rows):
  assert (scrub(new,old) if key(new) in by_key else new)==old,key(new)
 write(ROOT/'site_data.json',root_rows)
 snapshot=copy.deepcopy(before['web/menu_exchange_snapshot.json'])
 for e in snapshot['entries']:
  if tuple(e['key']) in by_key:e['exchangeUnits']=copy.deepcopy(by_key[tuple(e['key'])]['exchangeUnits'])
 snapshot['sourceSha256']=hashlib.sha256((ROOT/'web/site_data.json').read_bytes()).hexdigest()
 write(ROOT/'web/menu_exchange_snapshot.json',snapshot)
 trays=copy.deepcopy(before['month_lunch_trays.json'])
 for tray in trays:
  if key(tray) not in by_key:continue
  row=row_map[key(tray)];eu=row['exchangeUnits'];db=eu['matchedDb']
  tray['식품교환단위']={**{kr:eu[en] for en,kr in GROUPS.items()},'미매칭_항목':eu['unmatched'],
   'recipeNotes':eu['recipeNotes'],'externalRecipes':eu['externalRecipes'],
   '매칭DB':{'menugen':db['menugen'],'recipe_db':db['recipeDb'],'db104_direct':db['db104']}}
  patches={p['display']:p for p in by_key[key(tray)]['itemOverrides']}
  for item in tray.get('item_detail',[]):item.update(copy.deepcopy(patches.get(item['display'],{})))
 write(ROOT/'month_lunch_trays.json',trays)
 # Existing manual entries outside these meals are byte-for-byte equal as JSON values.
 after_manual={tuple(e['key']):e for e in manual['entries']}
 for e in before['manual_exchange_overrides.json']['entries']:
  if tuple(e['key']) not in by_key:assert e==after_manual[tuple(e['key'])]
 receipt={'status':'applied_to_runtime','applied':'2026-11-11','sourceCommit':read(BUNDLE/'manifest.json')['sourceCommit'],
  'userPreference':'앞으로 GitHub 업로드 시 검토 기록·실행 데이터·재계산·웹사이트 배포까지 함께 진행',
  'recipes':6,'excludedItems':3,'meals':6,'nutritionChanged':False,'preflight':preflight,
  'resultSha256':{f:hashlib.sha256((ROOT/f).read_bytes()).hexdigest() for f in FILES}}
 write(receipt_path,receipt)
 print(json.dumps({k:v for k,v in receipt.items() if k!='resultSha256'},ensure_ascii=False))
if __name__=='__main__':apply()
