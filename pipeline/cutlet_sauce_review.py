"""User-approved 30g sauce for plain pork cutlets with no sauce already recorded."""
from functools import lru_cache

# Broth dishes, curry, aqua salad sauce, and rose sauce must not get a second sauce.
PLAIN_CUTLETS = {
    '등심돈까스', '치즈돈까스', '고구마치즈돈까스', '왕돈가스',
    '왕돈가스*눈꽃치즈', '왕돈까스', '⭐️특식⭐️한양돈까스', '고구마무스돈까스',
}
CODE = 'P113-206020400-7705'


@lru_cache(maxsize=1)
def sauce_match():
    from gagong_search import load_db
    from prepared_food_overrides import PRODUCT_FIELDS, number
    row = next(r for r in load_db() if r['식품코드'] == CODE)
    if row['영양성분함량기준량'] != '100g' or row['식품소분류명'] != '소스':
        raise ValueError('돈까스소스 제품의 함량 기준·제품 유형 확인 필요')
    return {
        'source': 'gagong_db', 'name': row['식품명'], 'unit': 'g', 'basis': '100g',
        'code': CODE, 'per100': {f: number(row.get(col)) for f, col in PRODUCT_FIELDS.items()},
        'nutrition_note': (
            '사용자 승인: 누락된 일반 돈까스 동반 소스를 임시30g으로 추가. '
            '가공식품DB 돈까스소스(순한맛), (주)놀부, P113-206020400-7705 '
            '(100g당95kcal) 단일 제품을 대체 자료로 지정; 30g당28.5kcal. '
            '실제 제공 제품·분량 확인값 아님. 기존 소스 또는 로제·카레·나베 등에 중복 추가하지 않음. '
            '영양성분에는 당류·탄수화물·지방·나트륨 등 알려진 성분을 포함하고 결측을 표시. '
            '식품교환단위는 기존 사용자 지정 소스 제외 규칙 유지. 원본 메인 메뉴명·사진 유지.'
        ),
    }


def needs_sauce(items, lunch):
    if lunch['main'] not in PLAIN_CUTLETS:
        return False
    return not any(any(word in item['display'] for word in ('소스', '브라운', '로제'))
                   for item in items)


def apply_cutlet_sauce(items, lunch):
    if not needs_sauce(items, lunch):
        return
    from build_month import build_item
    match = sauce_match()
    sauce = build_item('돈까스소스', 30, '사용자 승인 누락 돈까스소스 임시30g', {'돈까스소스': match})
    sauce['nutritionFoodCode'] = CODE
    sauce['exchange_excluded_reason'] = '돈까스소스: 사용자 지정 소스 교환단위 제외 유지. 영양성분에는 임시30g을 포함.'
    items.append(sauce)
