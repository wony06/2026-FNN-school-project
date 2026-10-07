"""Apply existing exchange calculations to the requested two restaurants and date range.

Use stored per-item portions; retain all nutritional values and existing plaza data.
Run from any directory with Python. Writes a calculation audit in outputs/.
"""
import copy
import csv
import hashlib
import json
from pathlib import Path
from build_month import compute_tray_exchanges
from exchange_unit import compute_exchange_units, EXCHANGE_GROUPS, compute_kimchi_pair, KIMCHI_PAIR_EXCLUDED_DATES

ROOT = Path(__file__).resolve().parent.parent
FIELDS = dict(zip(EXCHANGE_GROUPS, ['grain', 'meat', 'veg', 'fat', 'dairy', 'fruit']))
EXCLUDED = {'우동국', '우동국물', '미소국', '미소장국', '케찹', '케첩', '간장', '초간장', '초장', '돈까스소스', '브라운소스', '쌈장'}

def selected(row):
    return row['shop'] in ('401', '204') and '2026-08-24' <= row['date'] <= '2026-09-19'

def load(path):
    return json.loads(path.read_text(encoding='utf-8'))

def key(row):
    return (row['date'], row['shop'], row['category'], row['main'])

def to_web(eu):
    src = eu['매칭DB']
    return {**{en: eu[kr] for kr, en in FIELDS.items()},
            'unmatched': eu['미매칭_항목'], 'externalRecipes': eu['externalRecipes'],
            'recipeNotes': eu['recipeNotes'],
            'matchedDb': {'menugen': src['menugen'], 'recipeDb': src['recipe_db'], 'db104': src['db104_direct']}}

def run():
    web_path = ROOT / 'web/site_data.json'
    web = load(web_path)
    before = copy.deepcopy(web)
    changed, audit = {}, []
    for row in web:
        if not selected(row):
            continue
        items = [dict(item, display=item.get('calculationName',item['display']), weight_g=item.get('exchange_weight_g',item['weight_g'])) for item in row['itemDetails']]
        eu = compute_tray_exchanges(items, row.get('calculationMain',row['main']), row['shop'], row['date'])
        eu['recipeNotes'].insert(0, '한양플라자와 동일한 식품군 분류·재료 DB 매칭·환산식 적용. 제공량은 해당 식당의 기존 항목별 추정 중량이며 실측값이 아님. 미매칭 재료는 합계에 미반영되어 과소 추정될 수 있음.')
        # Verify independently that the six displayed totals sum the item results.
        totals = {g: 0 for g in EXCHANGE_GROUPS}
        for item in items:
            if item.get('exchange_excluded_reason'):
                audit.append({'date':row['date'],'shop':row['shop'],'main':row['main'],'item':item['display'],'matched':False,'excluded':True,'reason':item['exchange_excluded_reason'],'weight_g':item['weight_g'],'units':{g:0 for g in EXCHANGE_GROUPS}})
                continue
            if row['shop'] == '401' and item['display'] == '김치2종' and row['date'] in KIMCHI_PAIR_EXCLUDED_DATES:
                audit.append({'date':row['date'],'shop':row['shop'],'main':row['main'],'item':'김치2종','matched':False,'reason':'사진 부재: 사용자 지정으로 미매칭 유지','weight_g':item['weight_g'],'units':{g:0 for g in EXCHANGE_GROUPS}})
                continue
            if item['display'] in EXCLUDED:
                continue
            result = compute_kimchi_pair(row['date'], item['weight_g']) if row['shop']=='401' and item['display']=='김치2종' else None
            if result is None:
                result = compute_exchange_units(item['display'], item['weight_g'], use_plaza_servings=False)
            if result['matched']:
                for group in EXCHANGE_GROUPS:
                    totals[group] += result['units'][group]
            audit.append({'date': row['date'], 'shop': row['shop'], 'main': row['main'],
                          'item': item['display'], 'weight_g': item['weight_g'],
                          'matched': result['matched'], 'source': result.get('source'),
                          'unresolved_ingredients': result.get('unresolved_ingredients', []),
                          'units': result['units']})
        assert all(eu[g] == round(totals[g], 2) for g in EXCHANGE_GROUPS)
        row['exchangeUnits'] = to_web(eu)
        changed[key(row)] = eu

    for old, new in zip(before, web):
        if selected(new):
            assert {k: v for k, v in old.items() if k != 'exchangeUnits'} == {k: v for k, v in new.items() if k != 'exchangeUnits'}
        else:
            assert old == new

    snapshot_path = ROOT / 'web/menu_exchange_snapshot.json'
    snapshot = load(snapshot_path)
    original_snapshot = copy.deepcopy(snapshot)
    found = set()
    for entry in snapshot['entries']:
        k = tuple(entry['key'])
        if k in changed:
            entry['exchangeUnits'] = to_web(changed[k])
            found.add(k)
    for k in changed.keys() - found:
        snapshot['entries'].append({'key': list(k), 'sourceMain': k[3], 'exchangeUnits': to_web(changed[k])})
    assert len({tuple(e['key']) for e in snapshot['entries']}) == len(snapshot['entries'])
    for old in original_snapshot['entries']:
        if tuple(old['key']) not in changed:
            assert old == next(e for e in snapshot['entries'] if e['key'] == old['key'])

    # Update existing generated data files without rebuilding nutrition or older dates.
    for p in [ROOT / 'month_lunch_trays.json', ROOT / 'site_data.json']:
        data = load(p)
        for row in data:
            if key(row) in changed:
                if p.name == 'month_lunch_trays.json':
                    row['식품교환단위'] = changed[key(row)]
                else:
                    row['exchangeUnits'] = to_web(changed[key(row)])
        p.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding='utf-8')

    web_path.write_text(json.dumps(web, ensure_ascii=False), encoding='utf-8')
    snapshot['source'] = '기존 한양플라자 스냅샷 유지; 2026-08-24~2026-09-19 생활과학대학·신소재공학관 동일 계산 확장'
    snapshot['sourceSha256'] = hashlib.sha256(web_path.read_bytes()).hexdigest()
    snapshot_path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=1), encoding='utf-8')

    output = ROOT.parents[2] / 'outputs'
    output.mkdir(exist_ok=True)
    (output / 'exchange-calculation-audit.json').write_text(json.dumps(audit, ensure_ascii=False, indent=2), encoding='utf-8')
    with (output / 'food-exchange-0824-0919.csv').open('w', encoding='utf-8-sig', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['날짜', '식당', '구분', '메인메뉴', *EXCHANGE_GROUPS, '미매칭항목'])
        for row in web:
            if selected(row):
                eu = row['exchangeUnits']
                writer.writerow([row['date'], row['shopName'], row['category'], row['main'],
                                 *[eu[FIELDS[g]] for g in EXCHANGE_GROUPS], ' / '.join(eu['unmatched'])])
    summary = {'menus': len(changed), 'byShop': {shop: sum(k[1] == shop for k in changed) for shop in ('401','204')},
               'fullyMatched': sum(not v['미매칭_항목'] for v in changed.values()),
               'withUnmatched': sum(bool(v['미매칭_항목']) for v in changed.values()),
               'unmatchedNames': sorted({n for v in changed.values() for n in v['미매칭_항목']})}
    print(json.dumps(summary, ensure_ascii=False))

if __name__ == '__main__':
    run()
