"""Apply the approved review bundle, scoped to its eight meals (idempotent)."""
import copy
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUNDLE = ROOT / 'exchange_matching_updates/2026-11-10_sinsojae_1109-1113'
GROUPS = {'grain':'곡류군','meat':'어육류군','veg':'채소군','fat':'지방군','dairy':'우유군','fruit':'과일군'}

def read(path):
    return json.loads(path.read_text(encoding='utf-8'))

def write(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=None if path.name=='site_data.json' else 1), encoding='utf-8')

def key(row):
    return tuple(row[f] for f in ('date','shop','category','main'))

def apply():
    changes = read(BUNDLE/'변경내역.json')['changes']
    recipes = read(ROOT/'custom_exchange_recipes.json')
    aliases = {}
    for change in changes:
        name = change['name']
        alias = '신소재_202611_검토확정_' + name
        aliases[name] = alias
        recipe = copy.deepcopy(change['recipe'])
        recipe['name'] = alias
        recipe['display_name'] = name
        recipe['assumptions'] = recipe['assumptions'].replace('웹사이트 반영 대기', '2026-11-11 사용자 승인으로 웹사이트 반영')
        existing = next((i for i,r in enumerate(recipes) if r['name']==alias), None)
        if existing is None:
            recipes.append(recipe)
        else:
            recipes[existing] = recipe
    write(ROOT/'custom_exchange_recipes.json', recipes)
    # Import only after writing: the exchange engine caches the custom recipes.
    from build_month import compute_tray_exchanges
    rows = read(ROOT/'web/site_data.json')
    original = copy.deepcopy(rows)
    by_key = {key(r):r for r in rows}
    targets = {tuple(c['key']) for c in changes}
    for change in changes:
        row = by_key[tuple(change['key'])]
        item = next(i for i in row['itemDetails'] if i['display']==change['name'])
        item['calculationName'] = aliases[change['name']]
        item['exchange_weight_g'] = change['recipe']['weight_g']
        item['exchange_weight_note'] = '2026-11-11 사용자 승인 검토 배합 적용. 영양성분 계산은 유지.'
    manual = read(ROOT/'manual_exchange_overrides.json')
    for row in rows:
        if key(row) not in targets:
            continue
        raw = compute_tray_exchanges(row['itemDetails'], row['main'], row['shop'], row['date'])
        db = raw['매칭DB']
        eu = {en:raw[kr] for en,kr in GROUPS.items()}
        eu.update(unmatched=raw['미매칭_항목'], externalRecipes=raw['externalRecipes'],
                  recipeNotes=raw['recipeNotes'], matchedDb={'menugen':db['menugen'],'recipeDb':db['recipe_db'],'db104':db['db104_direct']})
        eu['customRecipes'] = [copy.deepcopy(c['recipe']) for c in changes if tuple(c['key'])==key(row)]
        for recipe in eu['customRecipes']:
            recipe['assumptions'] = recipe['assumptions'].replace('웹사이트 반영 대기','2026-11-11 사용자 승인으로 웹사이트 반영')
        row['exchangeUnits'] = eu
        entry = next((e for e in manual['entries'] if tuple(e['key'])==key(row)), None)
        if entry is None:
            entry = {'key':list(key(row))}
            manual['entries'].append(entry)
        entry['exchangeUnits'] = copy.deepcopy(eu)
        patches = {p['display']:p for p in entry.get('itemOverrides',[])}
        for item in row['itemDetails']:
            if item.get('calculationName') in aliases.values():
                patches.setdefault(item['display'], {'display':item['display']}).update({f:item[f] for f in ('calculationName','exchange_weight_g','exchange_weight_note')})
        entry['itemOverrides'] = list(patches.values())
    # Only exchange fields and the 16 approved item metadata patches may change.
    for before, after in zip(original,rows):
        scrub = copy.deepcopy(after)
        if key(after) in targets:
            scrub['exchangeUnits'] = before['exchangeUnits']
            for old,new in zip(before['itemDetails'],scrub['itemDetails']):
                for field in ('calculationName','exchange_weight_g','exchange_weight_note'):
                    if field in old: new[field]=old[field]
                    else: new.pop(field,None)
        assert before==scrub, key(after)
    write(ROOT/'manual_exchange_overrides.json', manual)
    write(ROOT/'web/site_data.json', rows)
    root_rows = read(ROOT/'site_data.json')
    for i,row in enumerate(root_rows):
        if key(row) in targets: root_rows[i]=copy.deepcopy(by_key[key(row)])
    write(ROOT/'site_data.json', root_rows)
    snapshot = read(ROOT/'web/menu_exchange_snapshot.json')
    for entry in snapshot['entries']:
        if tuple(entry['key']) in targets:
            entry['exchangeUnits'] = copy.deepcopy(by_key[tuple(entry['key'])]['exchangeUnits'])
    snapshot['sourceSha256'] = hashlib.sha256((ROOT/'web/site_data.json').read_bytes()).hexdigest()
    write(ROOT/'web/menu_exchange_snapshot.json', snapshot)
    trays = read(ROOT/'month_lunch_trays.json')
    for tray in trays:
        if key(tray) not in targets: continue
        row=by_key[key(tray)]; eu=row['exchangeUnits']; db=eu['matchedDb']
        tray['식품교환단위'] = {**{kr:eu[en] for en,kr in GROUPS.items()},'미매칭_항목':eu['unmatched'],
            'externalRecipes':eu['externalRecipes'],'recipeNotes':eu['recipeNotes'],
            '매칭DB':{'menugen':db['menugen'],'recipe_db':db['recipeDb'],'db104_direct':db['db104']}}
        patches={i['display']:i for i in row['itemDetails']}
        for item in tray.get('item_detail',[]):
            patch=patches[item['display']]
            for field in ('calculationName','exchange_weight_g','exchange_weight_note'):
                if field in patch: item[field]=patch[field]
    write(ROOT/'month_lunch_trays.json', trays)
    print('Applied 15 recipes / 16 items / 8 meals; nutrition and other meals preserved.')
    for row in rows:
        if key(row) in targets: print(key(row), {g:row['exchangeUnits'][g] for g in GROUPS}, row['exchangeUnits']['unmatched'])

if __name__ == '__main__':
    apply()
