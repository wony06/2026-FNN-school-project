"""Approved ingredient and nutrition corrections for reviewed November 26 meals."""
PREFIX = '검토_20261126_'
TARGETS = {
    ('2026-11-26', '204', '닭칼국수'),
    ('2026-11-26', '204', '스팸마요덮밥'),
    ('2026-11-26', '105', '순살안동찜닭덮밥'),
    ('2026-11-26', '105', '훈제오리김치찜'),
    ('2026-11-26', '105', '등심돈까스'),
}


def apply_reviewed_nov26_photos(items, lunch):
    if (lunch['date'], str(lunch['shop']), lunch['main']) not in TARGETS:
        return
    from build_month import build_item, NUT_FIELDS
    from prepared_food_overrides import prepared_food_override
    from recipe_decompose import DB104_MAP

    def prepared(recipe, display, weight):
        alias = PREFIX + recipe
        match = prepared_food_override(alias, [], [], NUT_FIELDS, DB104_MAP)
        if match is None:
            raise ValueError(f'Approved November 26 recipe missing: {alias}')
        result = build_item(alias, weight, '11/26 사진 기반 사용자 승인 임시 분량', {alias: match})
        result.update(display=display, calculationName=alias, nutritionRecipe=alias)
        return result

    if lunch['main'] == '닭칼국수':
        from auto_match import FOOD_DB
        code = 'D303-174100000-0001'
        food = next(r for r in FOOD_DB if r['code'] == code)
        if food['basis'] != '100g':
            raise ValueError('완성 닭칼국수 분석값의 100g 기준 확인 필요')
        note = ('11/26 신소재 닭칼국수 사용자 승인: 즉석조리·생면·숙면 제품 혼합 중앙값 대신 '
                '외식 분석함량 칼국수_닭고기(D303-174100000-0001, 100g당74kcal)를 단일 대체 자료로 지정. '
                '국물 포함 기존 제공량497g 유지. 면·닭고기·국물이 포함된 완성음식이므로 별도 재료를 중복 가산하지 않음. '
                '흑미밥·반찬·식품교환단위·원본 메뉴명·사진 유지. 실제 급식 배합·면/고기/국물 비율·제공량 미확인 대체 추정. '
                '이번 변경은 영양성분만이며 기존 교환단위 배합과 동일한 음식 배합으로 확인된 것은 아님.')
        match = {'source': 'food_db', 'name': food['name'], 'per100': food['n'],
                 'code': code, 'basis': food['basis'], 'nutrition_note': note}
        for index, item in enumerate(items):
            if item['display'] == '닭칼국수':
                replacement = dict(item)
                replacement.update(build_item(item['display'], 497, '국물 포함 완성 닭칼국수497g 대체',
                                              {item['display']: match}))
                replacement['nutritionFoodCode'] = code
                items[index] = replacement
        return

    if lunch['main'] == '스팸마요덮밥':
        for item in items:
            if item['display'] == '콘샐러드':
                item['calculationName'] = PREFIX + '콘샐러드_마요반영'
                item['exchange_weight_g'] = 71
                item['exchange_weight_note'] = '교환단위만 임시 배분: 옥수수60g+마요네즈11g. 영양성분은 기존 완성식품DB 유지.'
            elif item['display'] == '불닭고로케':
                item['calculationName'] = PREFIX + '불닭고로케_제품간이환산'
        return

    if lunch['main'] == '순살안동찜닭덮밥':
        for index, item in enumerate(items):
            if item['display'] == '닭찜_안동찜닭':
                items[index] = prepared('안동찜닭_떡치즈제외', item['display'], 208)
        return

    if lunch['main'] == '훈제오리김치찜':
        if not any(i['display'] == '두부' for i in items):
            items.insert(1, prepared('추가두부', '두부', 80))
        return

    for index, item in enumerate(items):
        if item['display'] == '샐러드':
            items[index] = prepared('잎채소샐러드드레싱', '샐러드', 71)
        elif item['display'] in ('김치', '깍두기'):
            items[index] = prepared('깍두기', '깍두기', item['weight_g'])
    if not any(i['display'] == '푸실리 반찬' for i in items):
        salad_index = next(index for index, item in enumerate(items) if item['display'] == '샐러드')
        items.insert(salad_index + 1, prepared('푸실리반찬', '푸실리 반찬', 35.5))
