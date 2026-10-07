"""Keep archived dates and user-approved exchange corrections during export."""
import copy
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
GROUPS = {'grain':'곡류군','meat':'어육류군','veg':'채소군','fat':'지방군','dairy':'우유군','fruit':'과일군'}

def key(row):
    return tuple(row[field] for field in ('date','shop','category','main'))

def read_optional(name, default):
    path = ROOT/name
    return json.loads(path.read_text(encoding='utf-8')) if path.exists() else default

def preserved_rows(rows):
    current = {key(row):row for row in rows}
    for row in read_optional('historical_site_data.json', []):
        current.setdefault(key(row), copy.deepcopy(row))
    for entry in read_optional('manual_exchange_overrides.json', {'entries':[]})['entries']:
        row = current.get(tuple(entry['key']))
        if row is None:
            continue
        row['exchangeUnits'] = copy.deepcopy(entry['exchangeUnits'])
        details = {item['display']:item for item in row.get('itemDetails', [])}
        for patch in entry.get('itemOverrides', []):
            if patch['display'] in details:
                details[patch['display']].update(copy.deepcopy(patch))
    return sorted(current.values(), key=key)

def sync_preserved_exchanges(rows):
    by_key = {key(row):row for row in rows}
    snapshot = read_optional('web/menu_exchange_snapshot.json', {'entries':[]})
    entries = {tuple(entry['key']):entry for entry in snapshot['entries']}
    for row in rows:
        if row.get('exchangeUnits') is not None:
            entries[key(row)] = {'key':list(key(row)), 'sourceMain':row['main'], 'exchangeUnits':row['exchangeUnits']}
    snapshot['entries'] = list(entries.values())
    snapshot['sourceSha256'] = hashlib.sha256((ROOT/'web/site_data.json').read_bytes()).hexdigest()
    (ROOT/'web/menu_exchange_snapshot.json').write_text(json.dumps(snapshot,ensure_ascii=False,indent=1),encoding='utf-8')
    trays = read_optional('month_lunch_trays.json', [])
    for tray in trays:
        row = by_key.get(key(tray))
        if row is None or row.get('exchangeUnits') is None:
            continue
        eu = row['exchangeUnits']
        db = eu.get('matchedDb', {})
        tray['식품교환단위'] = {**{kr:eu[en] for en,kr in GROUPS.items()},
            '미매칭_항목':eu.get('unmatched',[]), 'externalRecipes':eu.get('externalRecipes',[]),
            'recipeNotes':eu.get('recipeNotes',[]),
            '매칭DB':{'menugen':db.get('menugen',[]),'recipe_db':db.get('recipeDb',[]),'db104_direct':db.get('db104',[])}}
        patches = {item['display']:item for item in row.get('itemDetails', [])}
        for item in tray.get('item_detail', []):
            patch = patches.get(item['display'], {})
            for field in ('calculationName','exchange_weight_g','exchange_weight_note','exchange_excluded_reason'):
                if field in patch: item[field]=patch[field]
    (ROOT/'month_lunch_trays.json').write_text(json.dumps(trays,ensure_ascii=False,indent=1),encoding='utf-8')
