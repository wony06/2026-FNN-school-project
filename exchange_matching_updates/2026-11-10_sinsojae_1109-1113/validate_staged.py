"""Read-only checks for the staged November exchange review bundle."""
import copy
import hashlib
import json
import math
import sys
from pathlib import Path

sys.dont_write_bytecode = True
BUNDLE = Path(__file__).resolve().parent
ROOT = BUNDLE.parents[1]
GROUPS = {'grain':'곡류군','meat':'어육류군','veg':'채소군','fat':'지방군','dairy':'우유군','fruit':'과일군'}

def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))

def key(row):
    return tuple(row[field] for field in ('date','shop','category','main'))

def close(a, b):
    return math.isclose(a, b, rel_tol=0, abs_tol=1e-9)

protected = [ROOT / p for p in ('site_data.json','web/site_data.json','web/menu_exchange_snapshot.json','month_lunch_trays.json','custom_exchange_recipes.json','manual_exchange_overrides.json')]
before = [hashlib.sha256(p.read_bytes()).hexdigest() for p in protected]
manifest = read(BUNDLE / 'manifest.json')
assert manifest['appliedToRuntime'] is False
recipes = read(BUNDLE / 'custom_exchange_recipes_patch.json')
changes = read(BUNDLE / '변경내역.json')['changes']
projections = read(BUNDLE / 'manual_exchange_overrides_patch.json')['entries']
assert len(recipes) == 15 and len(changes) == 16 and len(projections) == 8
assert len({r['name'] for r in recipes}) == len(recipes)
assert not {'바질크림떡볶이','야채춘권','로제마라소스_통합'} & {r['name'] for r in recipes}
site = {key(r):r for r in read(ROOT / 'web/site_data.json')}
baseline = {key(r):r for r in read(BUNDLE / 'baseline_rows.json')}
assert len(baseline) == 10
for k, expected in baseline.items():
    assert site[k] == expected, f'Target row changed; rebase required: {k}'

sys.path.insert(0, str(ROOT / 'pipeline'))
import exchange_unit as engine

existing = read(ROOT / 'custom_exchange_recipes.json') + read(ROOT / 'external_exchange_recipes.json')
collisions = {r['name'] for r in recipes} & {r['name'] for r in existing}
assert not collisions, f'Existing recipe names need manual review: {collisions}'
computed = {}
for recipe in recipes:
    assert recipe['scale_to_target'] is True
    assert close(sum(i['weight_g'] for i in recipe['ingredients']), recipe['weight_g']), recipe['name']
    units = {g:0.0 for g in engine.EXCHANGE_GROUPS}
    for ingredient in recipe['ingredients']:
        record = engine.DB104_BY_NAME.get(ingredient['food_name'])
        mapped = engine.FOOD_GROUP_MAP.get(ingredient['food_group'])
        if mapped is not None:
            assert record is not None, ingredient['food_name']
        engine._add_ingredient(units, ingredient['food_group'], record, ingredient['weight_g'])
    computed[recipe['name']] = {en:units[kr] for en,kr in GROUPS.items()}

recipe_by_name = {r['name']:r for r in recipes}
expected_trays = {tuple(e['key']):copy.deepcopy(baseline[tuple(e['key'])]['exchangeUnits']) for e in projections}
for change in changes:
    name = change['name']
    assert change['recipe'] == recipe_by_name[name]
    assert all(close(change['exchangeUnits'][g], computed[name][g]) for g in GROUPS), name
    k = tuple(change['key'])
    assert k[1] == '204' and '2026-11-09' <= k[0] <= '2026-11-13'
    tray = expected_trays[k]
    assert name in tray['unmatched'], (name,k)
    for g in GROUPS:
        # Match the JavaScript positive-value rounding used for staged projections.
        tray[g] = math.floor((tray[g] + computed[name][g] + 2.220446049250313e-16) * 100 + 0.5) / 100
    tray['unmatched'] = [n for n in tray['unmatched'] if n != name]

for projection in projections:
    expected = expected_trays[tuple(projection['key'])]
    actual = projection['exchangeUnits']
    assert all(close(actual[g], expected[g]) for g in GROUPS), projection['key']
    assert actual['unmatched'] == expected['unmatched'], projection['key']

warm = recipe_by_name['온모밀']
assert not any(i['food_name'].startswith('소고기,') for i in warm['ingredients'])
ratio_recipe = recipe_by_name['맛살마늘쫑볶음']
scape = next(i['weight_g'] for i in ratio_recipe['ingredients'] if i['food_name']=='마늘종, 꽃줄기, 데친것')
crab = next(i['weight_g'] for i in ratio_recipe['ingredients'] if i['food_name']=='게맛살, 어육함량이 낮은것')
assert close(scape/(scape+crab),0.45)
assert before == [hashlib.sha256(p.read_bytes()).hexdigest() for p in protected]
print('PASS: 15 recipes, 16 item changes, 8 cumulative meal projections, 10 unchanged source rows; runtime files untouched.')
