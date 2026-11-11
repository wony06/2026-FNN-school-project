"""2026-11-11 승인: 신소재 5개 메뉴의 교환단위 레시피를 영양소에도 사용.

날짜·식당·메뉴를 제한하며 기존 교환단위와 제공량은 변경하지 않는다.
소스 제품 선택은 계산용 대체 추정이며 실제 급식 제품의 확인이 아니다.
"""
import csv
import json
from functools import lru_cache
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGETS = {
    ('2026-11-09', '204', '불닭크림우동'): '신소재_추가검토_20261109_불닭크림우동',
    ('2026-11-12', '204', '온모밀'): '신소재_202611_검토확정_온모밀',
    ('2026-11-12', '204', '치즈맛감자'): '신소재_추가검토_20261112_치즈맛감자',
    ('2026-11-13', '204', '새우튀김덮밥'): '신소재_202611_검토확정_새우튀김덮밥',
    ('2026-11-13', '204', '짬뽕국물'): '신소재_202611_검토확정_짬뽕국물',
}
PRODUCT_CODES = {'불닭소스(제품 미확인)': 'P113-206020400-0455',
                 '코다노치즈시즈닝': 'P113-201020100-0750'}
NOTE = ('2026-11-11 사용자 승인으로 기존 교환단위용 추정 배합을 영양성분에도 적용. '
        '아래 배합 기록의 영양성분 유지/미매칭 유지 문구는 이전 교환단위 작업 당시 상태이며 이번 승인으로 대체됨. '
        '실제 급식의 실측 영양값이 아님. DB 미수록 성분은 결측으로 표시하며 합계·NRF는 알려진 값만으로 계산. ')


@lru_cache(maxsize=1)
def sources():
    recipes = {r['name']: r for r in json.loads((ROOT/'custom_exchange_recipes.json').read_text(encoding='utf-8'))}
    raw = {r['식품명']: r for r in json.loads((ROOT/'db104_raw_ingredients.json').read_text(encoding='utf-8'))}
    with (ROOT/'gagong_db_nrf63.csv').open(encoding='utf-8-sig', newline='') as f:
        products = {r['식품코드']: r for r in csv.DictReader(f)}
    return recipes, raw, products


def recipe_match(alias):
    from build_month import NUT_FIELDS
    from recipe_decompose import DB104_MAP
    from prepared_food_overrides import PRODUCT_FIELDS, number
    recipes, raw, products = sources()
    recipe = recipes[alias]
    total = dict.fromkeys(NUT_FIELDS, 0.0)
    missing = set()
    ingredients = []
    for ingredient in recipe['ingredients']:
        name, weight = ingredient['food_name'], ingredient['weight_g']
        if name == '물':
            continue
        if name in PRODUCT_CODES:
            code = PRODUCT_CODES[name]
            record, mapping = products[code], PRODUCT_FIELDS
            if record['영양성분함량기준량'] != '100g':
                raise ValueError(f'제품 기준량 변경: {code}')
            source = f'gagong_db:{code}:{record["식품명"]}'
        else:
            record, mapping = raw[name], DB104_MAP
            source = f'db104:{name}'
        values = {f: number(record.get(mapping[f])) for f in NUT_FIELDS}
        for field, value in values.items():
            if value is None:
                missing.add(field)
            else:
                total[field] += value * weight / 100
        ingredients.append({'name': name, 'weight_g': weight, 'source': source,
                            'per100': values})
    if abs(sum(i['weight_g'] for i in recipe['ingredients']) - recipe['weight_g']) > 1e-6:
        raise ValueError(f'재료합과 제공량 불일치: {alias}')
    note = NOTE + recipe['assumptions']
    if '불닭크림우동' in alias:
        note += (' 영양 계산용 불닭소스는 프로젝트 가공식품DB의 마트킹 불닭소스 '
                 'P113-206020400-0455(100g당235kcal·탄수45g·단백질3g·지방5g·당류43g·나트륨2055mg)로 대체. '
                 '실제 급식 제품 미확인. 닭고기 재료를 추가한 것이 아님.')
    return {'source': 'recipe_decompose', 'name': alias, 'unit': 'g',
            'per100': {f: v*100/recipe['weight_g'] for f, v in total.items()},
            'partial_missing_fields': sorted(missing), 'nutrition_note': note,
            'recipe_batch_g': recipe['weight_g'], 'nutrition_ingredients': ingredients}


def apply_approved_nutrition(items, lunch):
    from build_month import build_item
    for item in items:
        alias = TARGETS.get((lunch['date'], str(lunch['shop']), item['display']))
        if alias is None:
            continue
        match = recipe_match(alias)
        updated = build_item(item['display'], item['weight_g'], item['weight_note'], {item['display']: match})
        item.update(updated)
        item['nutritionRecipe'] = alias
        item['nutritionIngredients'] = match['nutrition_ingredients']
