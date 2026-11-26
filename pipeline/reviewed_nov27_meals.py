"""User-approved November 27 nutrition corrections, restricted to reviewed trays."""
from copy import deepcopy

PREFIX = '검토_20261127_'
TARGETS = {
    ('2026-11-23', '401', '북창동 순두부찌개'),
    ('2026-11-24', '401', '북창동 순두부찌개'),
    ('2026-11-25', '401', '북창동 순두부찌개'),
    ('2026-11-26', '401', '북창동 순두부찌개'),

    ('2026-11-27', '204', '로제돈까스'),
    ('2026-11-27', '204', '돈육순두부찌개'),
    ('2026-11-27', '401', '불고기낙지전골'),
    ('2026-11-27', '401', '북창동 순두부찌개'),
}


def apply_reviewed_nov27(items, lunch):
    key = (lunch['date'], str(lunch['shop']), lunch['main'])
    if key not in TARGETS:
        return
    from build_month import build_item, NUT_FIELDS
    from prepared_food_overrides import prepared_food_override
    from recipe_decompose import DB104_MAP

    def prepared(name, weight):
        alias = PREFIX + name
        match = prepared_food_override(alias, [], [], NUT_FIELDS, DB104_MAP)
        if match is None:
            raise ValueError(f'Approved nutrition recipe missing: {alias}')
        item = build_item(alias, weight, '사용자 승인 임시 배합', {alias: match})
        item['calculationName'] = alias
        item['nutritionRecipe'] = alias
        return item

    for index, old in enumerate(items):
        name = old['display']
        if lunch['main'] == '북창동 순두부찌개' and name == '북창동 순두부찌개':
            item = prepared('북창동순두부_달걀1개', 283)
        elif lunch['main'] == '로제돈까스' and name == '로제돈까스':
            # Rebuilds are idempotent: never add sauce twice to an already reviewed item.
            if old.get('calculationName') == PREFIX + name:
                continue
            if old['weight_g'] != 151:
                raise ValueError('Review cutlet portion before adding the approved 30g sauce')
            sauce = prepared('로제소스', 30)
            item = deepcopy(old)
            item['weight_g'] = 181
            item['contrib'] = {f: old['contrib'][f] + sauce['contrib'][f] for f in NUT_FIELDS}
            item['missing'] = sorted(set(old['missing']) | set(sauce['missing']))
            item['source'] = 'recipe_decompose'
            item['db_name'] = old['db_name'] + '151g + 로제소스30g(대체 배합)'
            item['weight_note'] += '; ' + sauce['weight_note'] + '; 돈까스151g+소스30g=181g, 기존 까스 성분 유지'
            item['calculationName'] = PREFIX + name
            item['nutritionRecipe'] = PREFIX + name
        elif lunch['main'] == '로제돈까스' and name == '참치푸실리샐러드':
            item = prepared(name, 71)
        elif lunch['main'] == '돈육순두부찌개' and name == '돈육순두부찌개':
            item = prepared(name, 283)
        elif lunch['main'] == '불고기낙지전골' and name in ('불고기', '낙지전골'):
            item = prepared('불고기' if name == '불고기' else '낙지전골_소고기제외',
                            70 if name == '불고기' else 213)
        else:
            continue
        item['display'] = name
        # Original names and the remaining sides are preserved.
        items[index] = item
