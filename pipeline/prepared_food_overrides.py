"""Explicit proxies that keep prepared meals separate from dry/concentrated products.



These are substitutions, not identifications of the cafeteria's actual products.

Original display names and source databases remain intact.

"""

import json

from pathlib import Path



ROOT = Path(__file__).resolve().parent.parent

# User-approved nutrition reuse of the already approved exchange recipes.
APPROVED_SIDE_NUTRITION = {
    '베이컨감자채전': '신소재_202611_검토확정_베이컨감자채전',
    '비엔나강정': '신소재_202611_검토확정_비엔나강정',
    '계란파국': '신소재_202611_검토확정_계란파국',
    '맛살마늘쫑볶음': '신소재_202611_검토확정_맛살마늘쫑볶음',
}

PRODUCT_FIELDS = {

    'kcal':'에너지(kcal)', 'protein':'단백질(g)', 'fat':'지방(g)',

    'carb':'탄수화물(g)', 'sugar':'당류(g)', 'fiber':'식이섬유(g)',

    'ca':'칼슘(mg)', 'fe':'철(mg)', 'vitA':'비타민 A(μg RAE)',

    'vitC':'비타민 C(mg)', 'satFat':'포화지방산(g)', 'na':'나트륨(mg)',

}

# Codes make these choices reproducible; do not reselect by lowest calories.

PRODUCTS = {

    '레몬홍차': ('P109-102010200-3383', 200, '액상차'),

    '매실차': ('P109-102010200-4034', 200, '액상차'),

    '크림스프': ('P123-206020200-0010', 150, '즉석섭취식품'),

}

COOKED = {
    '간장불고기': ('D708-375010000-0001', 151),
    '짜사이': ('D714-715000000-0001', 72.2),
    '소고기샤브샤브': ('D306-287180000-0001', 297),
    '건파래볶음': ('D710-498000000-0001', 80),
    '소고기콩나물밥': ('D701-047280000-0001', 417),

    '석류차': ('D220-719000000-0146', 200),
    '감자수제비국': ('D603-160520000-0001', 283),

    '유부우동국': ('D605-244000000-0001', 272),

}



def number(value):

    if value in (None, '', '-', 'Tr', 'tr'):

        return None

    try:

        return float(value)

    except (ValueError, TypeError):

        return None





def prepared_food_override(name, foods, products, nutrients, raw_map):

    if name in ('묵은지참치비빔밥', '갈릭쉬림프덮밥', '시금치치킨프리카세', '참치마요덮밥') or name in APPROVED_SIDE_NUTRITION:
        recipe_file = 'external_exchange_recipes.json' if name == '시금치치킨프리카세' else 'custom_exchange_recipes.json'
        recipe_name = APPROVED_SIDE_NUTRITION.get(name, name)
        recipe = next(r for r in json.loads((ROOT/recipe_file).read_text(encoding='utf-8')) if r['name'] == recipe_name)
        records = {r['식품명']:r for r in json.loads((ROOT/'db104_raw_ingredients.json').read_text(encoding='utf-8'))}
        totals = {f:0.0 for f in nutrients}; partial = set()
        for ingredient in recipe['ingredients']:
            if ingredient['food_name'] == '물':
                continue
            record = records.get(ingredient['food_name'])
            for f in nutrients:
                value = ingredient['nutrients_per100'].get(f) if 'nutrients_per100' in ingredient else number(record.get(raw_map[f]))
                if value is None: partial.add(f)
                else: totals[f] += value * ingredient['weight_g'] / 100
        return {'source':'recipe_decompose','name':name,'unit':'g',
                'per100':{f:v*100/recipe['weight_g'] for f,v in totals.items()},
                'partial_missing_fields':sorted(partial),'nutrition_note':recipe['assumptions'],
                'prepared_proxy':True,'recipe_batch_g':recipe['weight_g']}
    if name in ('우육면', '건두부무침'):
        recipe = next(r for r in json.loads((ROOT/'external_exchange_recipes.json').read_text(encoding='utf-8')) if r['name'] == name)
        records = {r['식품명']:r for r in json.loads((ROOT/'db104_raw_ingredients.json').read_text(encoding='utf-8'))}
        totals = {f:0.0 for f in nutrients}; partial = set()
        for ingredient in recipe['ingredients']:
            if ingredient['food_name'] == '물':
                continue
            record = records.get(ingredient['food_name'])
            for f in nutrients:
                value = ingredient['nutrients_per100'].get(f) if 'nutrients_per100' in ingredient else number(record.get(raw_map[f]))
                if value is None: partial.add(f)
                else: totals[f] += value * ingredient['weight_g'] / 100
        if name == '우육면': partial.update(nutrients)  # Unmeasured residual broth/seasoning.
        return {'source':'recipe_decompose','name':name,'unit':'g',
                'per100':{f:v*100/recipe['weight_g'] for f,v in totals.items()},
                'partial_missing_fields':sorted(partial),'nutrition_note':recipe['assumptions'],
                'prepared_proxy':True,'recipe_batch_g':recipe['weight_g'],'external_recipe_url':recipe['source_url']}
    if name in PRODUCTS:

        code, portion, subtype = PRODUCTS[name]

        row = next(r for r in products if r['식품코드'] == code)

        if row.get('식품소분류명') != subtype:

            raise ValueError(f'Prepared product subtype changed: {code}')

        note = (f'{name}: 분말·농축 제품과 혼합하지 않고 {subtype} 제품 {row["식품명"]}'

                f'({code}) 성분으로 대체 추정. 실제 급식 제품·희석비 미확인. '

                + ('완성 음료 성분을 최신 제공량 기준에 적용(밀도1 가정).' if subtype == '액상차'

                   else '최신 반찬 제공량에 즉석섭취식품 성분 적용.'))

        return {'source':'gagong_db', 'name':row['식품명'],

                'per100':{f:number(row.get(PRODUCT_FIELDS[f])) for f in nutrients},

                '_codes':[code], 'n_dup':1, 'is_concentrate':False,

                'serving_weight_g':portion, 'serving_weight_note':note,

                'nutrition_note':note, 'prepared_proxy':True,

                'basis':row.get('영양성분함량기준량'),

                'unit':'ml' if 'ml' in str(row.get('영양성분함량기준량')).lower() else 'g'}

    if name in COOKED:

        code, portion = COOKED[name]

        row = next(r for r in foods if r['code'] == code)

        detail = ('유부 고명 비율이 확인되지 않아 일식우동 완성 음식으로 대체. '

                  if name == '유부우동국' else '')

        note = (f'{name}: 면·수제비 제품 자체 대신 국물을 포함한 조리음식 {row["name"]}'

                f'({code}) 성분을 최신 단위별 국물 제공량에 적용. {detail}'

                '실제 건더기·국물 비율과 배합 미확인. 100mL 기준 자료는 밀도1로 환산.')

        if name == '유부우동국':
            note = (f'유부우동국: 사진에서 면이 확인되지 않는 곁들임 국. 면 포함 일식우동 대체를 제거하고 국물 포함 유부국({code}) 100mL당17kcal를 국 표준272mL에 적용. '
                    '실제 유부·육수·고명 배합과 제공량은 미확인 대체 추정. 교환단위도 면 없는 유부국으로 연결.')
        if name == '소고기샤브샤브':
            note = (f'샤브국수 조합의 국물·고기·채소 부분: 완성 음식 샤브샤브_소고기({code}) 100g당44kcal를 임시297g에 적용. '
                    '면은 별도 삶은 칼국수면200g만 포함하고 고기·채소를 영양성분에 다시 추가하지 않음. 실제 배합·제품·제공량 미확인 대체 추정.')
        if name == '간장불고기':
            note = ('간장불고기: 기존 산업체급식 돼지불고기_간장(D708-375010000-0001) 성분을 고정 사용. '
                    '김밥·도시락 등 이름에 간장불고기가 포함된 제품 중앙값으로 재매칭하지 않음. '
                    '소스9g 오분류를 메인 표준 추정151g으로 수정하고100mL 기준 성분에 밀도1(151mL) 가정 적용. 실제 밀도·제공량 미확인.')
        if name == '짜사이':
            note = '짜사이: 사용자 지정 짜사이무침(D714-715000000-0001) 완성 음식에 연결. 기존72.2g을 밀도1 가정으로72.2mL 환산. 실제 밀도·양념·제공량 미확인.'
        if name == '건파래볶음':
            note = (f'건파래볶음: 사용자 지정으로 산업체급식 파래볶음({code}) DB에 대체 연결. '
                    '100mL당49kcal를 기존 볶음 반찬 추정량80g에 밀도1(80mL)로 임시 환산해 적용. '
                    '원본 메뉴명과 기존 제공량은 유지. 실제 건파래의 수분·기름·양념·밀도 및 제품·제공량 미확인으로 건조 자반 형태와 차이가 있을 수 있음. '
                    '식품교환단위는 기존 사용자 지정 외부 레시피를 유지.')
        if name == '소고기콩나물밥':
            note = (f'소고기콩나물밥: 탄수화물1.8g/100g인 제품DB 대신 산업체급식 콩나물밥_소고기({code}) 완성 음식으로 대체. '
                    '100mL당131kcal를 덮밥 표준417mL에 적용. 밥·소고기·콩나물을 포함하므로 밥을 별도 가산하지 않음. 실제 제공량·배합 미확인.')
        if name == '석류차':
            note = (f'석류차: 농축 차 제품 대신 완성 음료 {row["name"]}({code})로 대체. '
                    '한 잔200mL 추정량에 100mL당 성분 적용. 실제 급식 제품·당도·희석비·제공량 미확인. '
                    '에이드나 무가당차가 아닌 석류향 차 음료를 대체 자료로 사용.')
        return {'source':'food_db', 'name':row['name'], 'origin':row['origin'],

                'code':code, 'per100':{f:row['n'].get(f) for f in nutrients},

                'serving_weight_g':portion, 'serving_weight_note':note,

                'nutrition_note':note, 'prepared_proxy':True, 'basis':row['basis'],

                'unit':'ml' if 'ml' in row['basis'].lower() else 'g'}

    if name == '칼국수면':
        record = next(r for r in json.loads((ROOT/'db104_raw_ingredients.json').read_text(encoding='utf-8')) if r['식품명']=='칼국수면, 생것, 삶은것')
        return {'source':'db104_direct', 'name':record['식품명'],
                'per100':{f:number(record.get(raw_map[f])) for f in nutrients}, 'unit':'g',
                'nutrition_note':'샤브국수 조합의 삶은 칼국수면: 원재료DB 칼국수면, 생것, 삶은것을 임시200g 적용. 건면·생면 성분에 삶은 중량을 곱하지 않음. 샤브 부분297g과 합497g 내 배분, 실제 면 제품·수분·제공량 미확인.'}
    if name == '적양배추':
        record = next(r for r in json.loads((ROOT/'db104_raw_ingredients.json').read_text(encoding='utf-8')) if r['식품명']=='양배추, 적색, 생것')
        return {'source':'db104_direct', 'name':record['식품명'],
                'per100':{f:number(record.get(raw_map[f])) for f in nutrients}, 'unit':'g',
                'nutrition_note':'사진의 생 적양배추: 양배추 음료 제품 매칭을 제거하고 원재료DB 양배추, 적색, 생것 사용. 기존 추정 중량29.3g 유지, 실제 중량 미확인.'}
    if name == '쥐어채볶음':
        recipe = next(r for r in json.loads((ROOT/'custom_exchange_recipes.json').read_text(encoding='utf-8')) if r['name']==name)
        records = {r['식품명']:r for r in json.loads((ROOT/'db104_raw_ingredients.json').read_text(encoding='utf-8'))}
        totals = {f:0.0 for f in nutrients}
        partial = set()
        for ingredient in recipe['ingredients']:
            record = records[ingredient['food_name']]
            for f in nutrients:
                value = number(record.get(raw_map[f]))
                if value is None:
                    partial.add(f)
                else:
                    totals[f] += value * ingredient['weight_g'] / 100
        return {'source':'recipe_decompose', 'name':name,
                'per100':{f:v*100/recipe['weight_g'] for f,v in totals.items()}, 'unit':'g',
                'partial_missing_fields':sorted(partial), 'nutrition_note':recipe['assumptions'],
                'prepared_proxy':True, 'recipe_batch_g':recipe['weight_g']}

    if name in ('수육국밥국물(밥·고기 제외)', '투움바떡볶이', '닭한마리전골'):
        recipe_file = 'external_exchange_recipes.json' if name == '닭한마리전골' else 'custom_exchange_recipes.json'
        recipe = next(r for r in json.loads((ROOT/recipe_file).read_text(encoding='utf-8')) if r['name'] == name)
        if name == '닭한마리전골':
            recipe['ingredients'] = recipe['ingredients'] + [{'food_name':'소금, 천일염, 가는소금', 'weight_g':recipe['conversion_assumptions']['salt_g']}]
            recipe['assumptions'] = ('닭한마리전골: 삶은 닭고기만으로 계산하던 매칭 대신 기존 교환단위 외부 레시피6884695의 국물 포함 대체 배합을 영양성분에도 적용. '
                '기준2627.5g 중 삶은 닭525g·감자300g·대파280g·마늘15g·배추218.9583g·삶은 칼국수437.9167g·소금7.5g·가정 육수843.125g. '
                '전골283g에 비례 환산하고 별도 양념장은9g 적용. 원문에 없는 배추·면은 기존 다른 날짜 사진 기반 보완이므로 11/2 실물 확인값 아님. '
                '뼈 가식부·조리수율·육수 잔존량·실제 배합은 미확인 추정. 육수 용출성분·미림·생강·후추의 잔존량 미반영(실제0으로 확인된 것이 아님). '
                '기준량과 가식부 변환은 기존 교환단위 레시피의 가정을 유지하며 소금7.5g은 영양성분에 포함. 밥은 별도 한 번만 계산.')
        records = {r['식품명']:r for r in json.loads((ROOT/'db104_raw_ingredients.json').read_text(encoding='utf-8'))}
        totals = {f:0.0 for f in nutrients}
        for ingredient in recipe['ingredients']:
            if ingredient['food_name'] == '물':
                continue
            record = records[ingredient['food_name']]
            for f in nutrients:
                value = number(record.get(raw_map[f]))
                if value is not None:
                    totals[f] += value * ingredient['weight_g'] / 100
        return {'source':'recipe_decompose', 'name':name,
                'per100':{f:v*100/recipe['weight_g'] for f,v in totals.items()},
                # Unknown broth can contribute every nutrient; don't present partial totals as complete.
                'partial_missing_fields':list(nutrients), 'nutrition_note':recipe['assumptions'],
                'prepared_proxy':True, 'recipe_batch_g':recipe['weight_g'], 'unit':'g'}

    if name == '제주고기국수':

        recipe = next(r for r in json.loads((ROOT/'custom_exchange_recipes.json').read_text(encoding='utf-8'))

                      if r['name'] == name)

        records = {r['식품명']:r for r in json.loads((ROOT/'db104_raw_ingredients.json').read_text(encoding='utf-8'))}

        totals = {f:0.0 for f in nutrients}

        partial = set()

        for ingredient in recipe['ingredients']:

            if ingredient['food_name'] in ('국물(물)', '국물(만능육수)'):

                continue

            record = records[ingredient['food_name']]

            for f in nutrients:

                value = number(record.get(raw_map[f]))

                if value is None:

                    partial.add(f)

                else:

                    totals[f] += value * ingredient['weight_g'] / 100

        note = ('제주고기국수: 건면 제품690g으로 계산하던 매칭을 제거하고 기존 사용자 제공 '

                '교환단위 레시피의 소면100g·삶은 돼지고기200g·채소·조미료 배합을 영양성분에도 적용. '

                f'국물 포함 배합{recipe["weight_g"]:g}g 대비 최신 면류 제공량으로 비례 환산. '

                '물200g·만능육수500g은 희석 중량에 포함하되 육수 영양정보가 없어 해당 기여는 미반영. '

                '소금15g 등 명시된 양념은 포함. 면 수분흡수·증발 미보정, 실제 제공량·배합 미확인.')

        return {'source':'recipe_decompose', 'name':'제주고기국수(사용자 제공 국물 포함 레시피)',

                'per100':{f:v*100/recipe['weight_g'] for f,v in totals.items()},

                'partial_missing_fields':sorted(partial), 'serving_weight_g':690,

                'serving_weight_note':note, 'nutrition_note':note, 'prepared_proxy':True,

                'recipe_batch_g':recipe['weight_g'], 'unit':'g'}

    return None

