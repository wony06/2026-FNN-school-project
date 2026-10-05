# -*- coding: utf-8 -*-
"""식품교환단위 산출: 메뉴 항목(이미 & / * 분해되고 중량이 정해진 원자 단위)을 재료 단위로
분해해 6개 식품군(곡류/어육류/채소/지방/우유/과일)별 교환단위수를 계산한다.

재료 소스 우선순위:
  1) MenuGen(농촌진흥청 국립식량과학원 "식단관리(메뉴젠) 음식,재료 및 조리 정보" API) - 메뉴명으로
     찾으면 재료명/중량/식품군이 이미 갖춰져 있음. 재료명이 db104(국가표준식품성분표)와 동일 출처라
     100% 그대로 매칭된다(2026-09-26 3,250건 표본 검증 완료).
  2) 실패 시 기존 recipe_decompose.py 인프라(recipe_db+db104)로 재료 분해.
  3) 그래도 실패하면 db104에서 메뉴명 자체를 원재료처럼 직접 검색(사과, 우유 등 그 자체가
     원재료인 단순 품목은 애초에 "레시피"가 아니라 MenuGen/recipe_db 어디에도 없기 때문).
셋 다 실패하면 matched=False로 반환(트레이 전체를 버리지 않고 그 항목만 미매칭 표시).

단위 산출 공식(대한당뇨병학회 식품교환표 "식품군별 영양소 기준" 그대로):
  곡류군 = 탄수화물(g)/23, 어육류군 = 단백질(g)/8, 채소군 = 탄수화물(g)/3,
  지방군 = 지방(g)/5, 우유군 = 탄수화물(g)/10, 과일군 = 탄수화물(g)/12
어육류군은 저/중/고지방 3단계 모두 단백질 8g으로 공통이라 등급 구분 없이 계산 가능.
"""
import os
import sys
import json

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from auto_match import GENERAL_SYNONYMS, PREFIX_STRIP_RULES
from ingredient_parser import parse_ingredients
from recipe_decompose import RECIPE_BY_NAME, match_ingredient_to_db104, find_db104_candidates, pick_db104_state, _norm

PROJECT_DIR = r"C:\Users\ST-USER\Desktop\2026 학술제"

with open(os.path.join(PROJECT_DIR, "db104_raw_ingredients.json"), encoding="utf-8") as f:
    DB104 = json.load(f)
DB104_BY_NAME = {}
for _r in DB104:
    DB104_BY_NAME.setdefault(_r["식품명"], _r)

with open(os.path.join(PROJECT_DIR, "menugen_recipes.json"), encoding="utf-8") as f:
    MENUGEN = json.load(f)
MENUGEN_BY_NAME = {}
for _d in MENUGEN:
    if _d.get("name"):
        MENUGEN_BY_NAME.setdefault(_d["name"], _d)

# 2026-09-27: MenuGen은 "김치찌개" 같은 순수 기본형이 없고 "김치찌개(돼지고기)"처럼
# 항상 괄호로 재료/변형을 붙여서만 등록돼 있는 경우가 많다(표본 확인: 8개 사례).
# 괄호 앞부분만 뗀 이름 -> [해당 변형 dish record들] 인덱스를 만들어, 메뉴명이 기본형
# 그대로일 때 괄호 벗긴 이름으로도 찾을 수 있게 한다.
MENUGEN_PAREN_BASE = {}
for _d in MENUGEN:
    _nm = _d.get("name") or ""
    if "(" in _nm:
        _base = _nm.split("(")[0].strip()
        if _base:
            MENUGEN_PAREN_BASE.setdefault(_base, []).append(_d)

# 변형이 여러 개일 때 대표로 고를 우선순위(일반적인 기본형에 가까운 것부터)
_VARIANT_PRIORITY = ["돼지고기", "소고기"]


def _pick_representative_variant(dishes):
    for kw in _VARIANT_PRIORITY:
        for d in dishes:
            if kw in (d.get("name") or ""):
                return d
    return sorted(dishes, key=lambda d: len(d.get("name") or ""))[0]

EXCHANGE_GROUPS = ["곡류군", "어육류군", "채소군", "지방군", "우유군", "과일군"]

# db104/MenuGen 두 소스에서 대분류 표기가 살짝 다른 경우(예: "감자류 및 전분류" vs
# "감자 및 전분류")까지 모두 등록. None = 계산 제외(자유식품) 또는 일괄 규칙이 없어
# 등장할 때마다 개별 검토가 필요한 카테고리(조리가공식품류/기타).
FOOD_GROUP_MAP = {
    "곡류 및 그 제품": "곡류군",
    "감자류 및 전분류": "곡류군", "감자 및 전분류": "곡류군",
    "육류 및 그 제품": "어육류군", "육류": "어육류군",
    "어패류 및 그 제품": "어육류군", "어패류 및 기타 수산물": "어육류군",
    "난류": "어육류군",
    "두류": "어육류군",
    "채소류": "채소군",
    "버섯류": "채소군",
    "해조류": "채소군",
    "유지류": "지방군",
    "견과류 및 종실류": "지방군", "견과 및 종실류": "지방군",
    "우유 및 그 제품": "우유군", "우유류 및 유제품": "우유군",
    "과일류": "과일군",
    "당류": None, "조미료류": None, "음료류": None, "주류": None, "차류": None,
    "조리가공식품류": None, "기타": None,
}

# 식품군별 1교환단위 기준 영양소/기준값(대한당뇨병학회 식품교환표 "식품군별 영양소 기준" 표)
UNIT_BASIS = {
    "곡류군": ("carb", 23), "어육류군": ("protein", 8), "채소군": ("carb", 3),
    "지방군": ("fat", 5), "우유군": ("carb", 10), "과일군": ("carb", 12),
}
DB104_NUT_COL = {"carb": "탄수화물", "protein": "단백질", "fat": "지방"}


def _nutrients_per100(record):
    out = {}
    for key, col in DB104_NUT_COL.items():
        v = record.get(col)
        try:
            out[key] = float(v)
        except (TypeError, ValueError):
            out[key] = 0.0
    return out


def _add_ingredient(units, raw_group_name, db104_record, weight_g):
    """재료 하나를 식품군에 배정하고 단위수를 더한다. 매핑/기록 없으면 False."""
    group = "지방군" if db104_record and db104_record.get("식품명", "").startswith("마요네즈") else FOOD_GROUP_MAP.get(raw_group_name)
    if group is None or db104_record is None:
        return False
    nut = _nutrients_per100(db104_record)
    field, basis = UNIT_BASIS[group]
    amount = nut[field] * weight_g / 100.0
    units[group] += amount / basis
    return True


def _lookup_menugen(name):
    if name in MENUGEN_BY_NAME:
        return MENUGEN_BY_NAME[name]
    alt = GENERAL_SYNONYMS.get(name)
    if alt and alt in MENUGEN_BY_NAME:
        return MENUGEN_BY_NAME[alt]
    for prefix in PREFIX_STRIP_RULES:
        if name.startswith(prefix) and len(name) > len(prefix):
            stripped = name[len(prefix):]
            if stripped in MENUGEN_BY_NAME:
                return MENUGEN_BY_NAME[stripped]
    if name in MENUGEN_PAREN_BASE:
        return _pick_representative_variant(MENUGEN_PAREN_BASE[name])
    return None


def _from_menugen(name, target_weight_g):
    spam_mayo = name == "스팸마요덮밥"
    no_meat = name == "청포묵무침"
    no_onion = name == "피쉬볼볶음"
    dish = _lookup_menugen("치킨마요덮밥" if spam_mayo else "어묵볶음(양파)" if no_onion else ("탕평채" if no_meat else name))
    if dish is None:
        return None
    ingredients = dish.get("ingredients") or []
    if spam_mayo:
        ingredients = [dict(i, food_name="햄, 통조림, 돼지고기 함유", food_group="육류", food_code=None)
                       if i.get("food_name", "").startswith("닭고기,") else i for i in ingredients]

    if no_meat:
        ingredients = [i for i in ingredients if i.get("food_group") not in ("육류", "육류 및 그 제품")]
    if no_onion:
        ingredients = [i for i in ingredients if not i.get("food_name", "").startswith("양파") ]
    if not ingredients:
        return None
    try:
        ref_weight = float(dish.get("weight_g") or 0)
    except (TypeError, ValueError):
        ref_weight = 0
    if no_meat or no_onion:
        ref_weight = sum(float(i.get("weight_g") or 0) for i in ingredients)
    scale = (target_weight_g / ref_weight) if ref_weight > 0 else 1.0

    if spam_mayo:
        scale = max(0.0, target_weight_g - 9.0) / (ref_weight - 2.0)
    units = {g: 0.0 for g in EXCHANGE_GROUPS}
    any_used = False
    unresolved = []
    for ing in ingredients:
        try:
            w = 9.0 if spam_mayo and ing.get("food_name") == "마요네즈" else float(ing.get("weight_g") or 0) * scale
        except (TypeError, ValueError):
            continue
        rec = DB104_BY_NAME.get(ing.get("food_name"))
        if _add_ingredient(units, ing.get("food_group"), rec, w):
            any_used = True
        else:
            unresolved.append(ing.get("food_name"))

    if not any_used:
        return None
    return {"units": units, "source": "menugen", "matched_name": dish.get("name"),
            "unresolved_ingredients": unresolved}


def _from_recipe_db(name, target_weight_g):
    r = RECIPE_BY_NAME.get(name)
    if r is None:
        return None
    parsed = parse_ingredients(r["ingredients"])
    items = parsed["items"]
    if name == "샐러드돈가스":
        items = [i for i in items if i["name"] != "튀김기름"]
    if not items:
        return None
    ref_weight = sum(it["amount_g"] for it in items)
    scale = (target_weight_g / ref_weight) if ref_weight > 0 else 1.0

    units = {g: 0.0 for g in EXCHANGE_GROUPS}
    any_used = False
    unresolved = []
    for ing in items:
        ingredient_name = ing["name"]
        if name == "샐러드돈가스":
            ingredient_name = {"돼지등심": "돼지고기, 등심, 생것", "빵가루": "밀, 빵가루",
                               "삶은 달걀": "달걀, 삶은것", "피클": "오이 피클",
                               "방울토마토": "토마토, 방울토마토, 생것",
                               "양상추": "상추, 결구(양상추), 녹색, 생것",
                               "어린잎채소": "비타민채(다채), 어린잎, 생것"}.get(ingredient_name, ingredient_name)

        if name == "펜네 파스타 샐러드":
            ingredient_name = {'펜넬파스타': '스파게티면, 말린것', '청피망': '피망, 초록색, 생것', '홍피망': '피망, 빨간색, 생것', '완두콩': '완두, 삶은것', '블랙올리브': '올리브 절임, 완숙, 검은색', '토마토콩카세': '토마토, 생것', '파마산치즈': '치즈, 파르메산(파마산)'}.get(ingredient_name, ingredient_name)
        if name == "삼색딤섬":
            ingredient_name = {'다진 소고기': '소고기, 한우(1등급), 살코기, 생것', '후춧가루': '후추, 검은색, 가루', '통깨': '참깨, 흰색, 말린것'}.get(ingredient_name, ingredient_name)
        exact_record = DB104_BY_NAME.get(ingredient_name)
        m = {"record": exact_record} if exact_record is not None else match_ingredient_to_db104(ingredient_name, r.get("way"))
        if m is None:
            unresolved.append(ing["name"])
            continue
        rec = m["record"]
        w = ing["amount_g"] * scale
        if _add_ingredient(units, rec.get("식품군"), rec, w):
            any_used = True
        else:
            unresolved.append(ing["name"])

    if not any_used:
        return None
    return {"units": units, "source": "recipe_db", "matched_name": name,
            "unresolved_ingredients": unresolved}


def _find_db104_contains(name):
    """db104 표기 순서가 우리 메뉴명과 다른 경우 대비(예: 메뉴명 '배추김치' vs db104의
    '김치, 배추 김치' - 첫 토큰이 '김치'라 find_db104_candidates의 첫토큰 매칭이 실패함).
    콤마를 뺀 전체 이름에 쿼리가 부분 문자열로 포함되는 후보를 찾는다."""
    q = _norm(name)
    if not q:
        return []
    return [r for r in DB104 if q in _norm(r["식품명"].replace(",", ""))]


def _from_direct_db104(name, weight_g):
    """메뉴명 자체가 이미 원재료인 경우(사과, 우유, 배추김치 등) - db104에서 찾아
    전체 중량을 그 재료 하나로 취급. 조리상태 우선순위 없이 기본값으로 시도."""
    cands, used_synonym = find_db104_candidates(name)
    if not cands:
        cands = _find_db104_contains(name)
    if not cands:
        return None
    rec, state = pick_db104_state(cands, None)
    if rec is None:
        return None
    units = {g: 0.0 for g in EXCHANGE_GROUPS}
    if not _add_ingredient(units, rec.get("식품군"), rec, weight_g):
        return None
    return {"units": units, "source": "db104_direct", "matched_name": rec["식품명"],
            "unresolved_ingredients": []}


# 2026-09-27: "수식어+기본요리" 조합형 메뉴명 중, 수식어를 떼어도 영양 왜곡이 거의 없다고
# 검토·확인된 것만 등록(사용자 검토: 22개 후보 중 재료 자체가 핵심 성분인 8개는 제외하고
# 조리스타일/부재료/브랜드명 수준인 14개만 채택). auto_match.py의 PREFIX_STRIP_RULES(돈육/왕)
# 와는 목적이 달라 섞지 않음 - 저긴 영양성분 매칭 전용이라 같이 쓰면 서로 다른 의도의 규칙이
# 얽혀 예상 못 한 부작용이 날 수 있어 분리해서 관리한다.
MENUGEN_MODIFIER_PREFIXES = [
    "가마보꼬", "교자", "데리야끼", "목살", "몽글", "물", "양념", "우삼겹",
    "치즈", "투움바", "햄", "로제", "초", "해초",
]


def _from_external_recipe(name, target_weight_g):
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "external_exchange_recipes.json")
    with open(path, encoding="utf-8") as f:
        recipes = json.load(f)
    dish = next((d for d in recipes if d["name"] == name), None)
    if dish is None:
        return None
    units = {g: 0.0 for g in EXCHANGE_GROUPS}
    scale = target_weight_g / dish["weight_g"]
    for ing in dish["ingredients"]:
        _add_ingredient(units, ing["food_group"], DB104_BY_NAME.get(ing["food_name"]), ing["weight_g"] * scale)
    return {"units": units, "source": "external_recipe", "matched_name": name, "unresolved_ingredients": [],
            "external_recipe": {"name": name, "url": dish["source_url"], "note": dish["assumptions"]}}


def _from_custom_recipe(name, target_weight_g):
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "custom_exchange_recipes.json")
    with open(path, encoding="utf-8") as f:
        recipes = json.load(f)
    dish = next((d for d in recipes if d["name"] == name), None)
    if dish is None:
        return None
    units = {g: 0.0 for g in EXCHANGE_GROUPS}
    scale = target_weight_g / dish["weight_g"]
    unresolved = []
    for ing in dish["ingredients"]:
        record = DB104_BY_NAME.get(ing["food_name"])
        if record is None and FOOD_GROUP_MAP.get(ing["food_group"]) is not None:
            unresolved.append(ing["food_name"])
        _add_ingredient(units, ing["food_group"], record, ing["weight_g"] * scale)
    return {"units": units, "source": "custom_recipe", "matched_name": name,
            "unresolved_ingredients": unresolved, "recipe_note": dish["assumptions"]}


def _try_cascade_exact(name, weight_g):
    result = _from_menugen(name, weight_g)
    if result is None:
        result = _from_recipe_db(name, weight_g)
    if result is None:
        result = _from_direct_db104(name, weight_g)
    return result


def _try_cascade(name, weight_g):
    variants = list(dict.fromkeys([name, name.replace("까스", "가스"), name.replace("가스", "까스")]))
    for candidate in variants:
        result = _try_cascade_exact(candidate, weight_g)
        if result is not None:
            return result
    return None


def compute_exchange_units(name, weight_g):
    """메뉴 항목 하나(원자 단위 이름) + 이미 산정된 중량(g)으로 6개 식품군 교환단위 계산.
    MenuGen -> recipe_db -> db104 직접매칭 순으로 시도. 다 실패하면 승인된 수식어 접두어를
    떼고 기본요리명으로 한 번 더 시도. 그래도 실패하면 matched=False."""
    if name == "차돌짬뽕밥":
        units = {g: 0.0 for g in EXCHANGE_GROUPS}
        for component, weight in (("차돌박이짬뽕국", 790.0), ("쌀밥", 275.0)):
            result = _from_menugen(component, weight)
            if result is None:
                return {"matched": False, "units": units, "source": None, "unresolved_ingredients": [component]}
            for group in EXCHANGE_GROUPS:
                units[group] += result["units"][group]
        return {"matched": True, "units": units, "source": "menugen",
                "matched_name": "차돌박이짬뽕국 + 쌀밥", "unresolved_ingredients": []}
    if name == "크랩알밥":
        units = {g: 0.0 for g in EXCHANGE_GROUPS}
        for component, weight in (("날치알밥", max(0.0, weight_g - 30.0)), ("게맛살", 30.0)):
            result = _from_menugen(component, weight)
            if result is None:
                return {"matched": False, "units": units, "source": None, "unresolved_ingredients": [component]}
            for group in EXCHANGE_GROUPS:
                units[group] += result["units"][group]
        return {"matched": True, "units": units, "source": "menugen",
                "matched_name": "날치알밥 + 게맛살", "unresolved_ingredients": []}
    if name in ("크림스프", "크림수프", "스프(크림)"):
        return {"matched": False, "units": {g: 0.0 for g in EXCHANGE_GROUPS},
                "source": None, "matched_name": "스프(크림)",
                "reason": "분말 제품 영양성분표 및 1인분 분말량 미확인으로 계산 보류(0 교환단위 아님)",
                "recipe_note": '크림스프: 사용자 확인에 따라 물에 분말을 풀어 만든 스프로 분류. 분말 제품의 영양성분표와 1인분 분말 사용량이 없어 식품교환단위 계산 보류. 미매칭 목록에 유지하며, 합계에 미반영된 것은 교환단위가 0이라는 의미가 아님. 우유·버터 기반 외부 레시피는 적용하지 않음.',
                "unresolved_ingredients": ["스프, 크림 스프, 가루, 끓인것"]}
    if name == "스팸마요덮밥":
        weight_g = 570.0
    if name in ("옹심이", "찹쌀옹심이"):
        # 사용자 지정 대체 가정: 가공식품 DB 탄수화물 52g/100g으로 곡류군 산출.
        units = {g: 0.0 for g in EXCHANGE_GROUPS}
        units["곡류군"] = weight_g * 52.0 / 100.0 / 23.0
        return {"matched": True, "units": units, "source": "gagong_estimate",
                "matched_name": "찹쌀옹심이", "unresolved_ingredients": []}
    if name in ("쌈채소", "쌈야채"):
        units = {g: 0.0 for g in EXCHANGE_GROUPS}
        record = DB104_BY_NAME.get("상추, 잎상추, 치마상추, 녹색, 생것")
        if _add_ingredient(units, "채소류", record, weight_g):
            return {"matched": True, "units": units, "source": "db104_direct",
                    "matched_name": "상추, 잎상추, 치마상추, 녹색, 생것", "unresolved_ingredients": []}
    if name == "부타동":
        units = {g: 0.0 for g in EXCHANGE_GROUPS}
        for component, weight in (("돼지고기 간장볶음", 220.0), ("쌀밥", 350.0)):
            result = _from_menugen(component, weight)
            if result is None:
                return {"matched": False, "units": units, "source": None, "unresolved_ingredients": [component]}
            for group in EXCHANGE_GROUPS:
                units[group] += result["units"][group]
        return {"matched": True, "units": units, "source": "menugen",
                "matched_name": "돼지고기 간장볶음 + 쌀밥", "unresolved_ingredients": []}
    if name in ("묵은지", "묵은 김치"):
        units = {g: 0.0 for g in EXCHANGE_GROUPS}
        record = DB104_BY_NAME.get("김치, 배추 김치")
        if _add_ingredient(units, "채소류", record, weight_g):
            return {"matched": True, "units": units, "source": "db104_direct",
                    "matched_name": "김치, 배추 김치", "unresolved_ingredients": []}
    # 이름만 연결한다. 완제품의 채소류 분류로 튀김옷까지 계산하지 않도록 보류한다.
    # 사용자 지정: 등심돈까스는 기본 돈가스 레시피로 계산한다.
    if name in ("등심돈까스", "등심돈가스"):
        name = "돈가스"
    # 사용자 지정: 비엔나케찹볶음는 소시지볶음(토마토케첩, 야채) 레시피로 계산한다.
    if name in ("비엔나케찹볶음", "비엔나케첩볶음"):
        name = "소시지볶음(토마토케첩, 야채)"
    # 사용자 지정: 오그락지는 무말랭이 무침 레시피로 계산한다.
    if name in ("오그락지", "무말랭이무침"):
        name = "무말랭이 무침"
    # 사용자 지정: 산고추지는 고추장아찌로 계산한다.
    if name == "산고추지":
        name = "고추장아찌"
    if name in ("숙주나물무침", "숙주나물 무침"):
        name = "숙주나물"
    if name in ("쫄깃단무지무침", "쫄깃단무지 무침"):
        name = "단무지"
    if name in ("마늘쫑장아찌", "마늘종장아찌"):
        name = "마늘종 장아찌"
    if name in ("떡고기산적조림", "떡고기산적 조림"):
        name = "퓨전떡갈비"
    if name == "딤섬":
        name = "삼색딤섬"
    if name == "통살치킨가스":
        name = "통살치킨까스"
    if name in ("대패삼겹살", "대패 삼겹살"):
        name = "삼겹살구이"
    if name in ("단무지무침", "단무지 무침"):
        name = "단무지"
    if name in ("고추잎무침", "고춧잎무침"):
        name = "고춧잎나물"
    if name in ("고기산적조림", "고기산적 조림"):
        name = "퓨전떡갈비"
    if name in ("견과류멸치볶음", "견과류 멸치볶음"):
        name = "멸치볶음(견과류)"
    if name in ("계란지단", "달걀지단"):
        units = {g: 0.0 for g in EXCHANGE_GROUPS}
        record = DB104_BY_NAME.get("달걀, 부침(달걀프라이)")
        if _add_ingredient(units, "난류", record, weight_g):
            return {"matched": True, "units": units, "source": "db104_direct",
                    "matched_name": "달걀, 부침(달걀프라이)", "unresolved_ingredients": []}
    if name in ("참치야채비빔밥", "참치 야채비빔밥"):
        name = "참치생야채비빔밥"
    if name == "주꾸미덮밥":
        name = "쭈꾸미볶음덮밥"
    if name in ("제육볶음", "제육 볶음"):
        name = "돼지고기볶음(고추장, 야채)"
    if name in ("알밥", "알 밥"):
        name = "날치알밥"
    if name == "아쿠아돈까스":
        name = "샐러드돈가스"
    if name in ("비프하이라이스", "비프 하이라이스"):
        name = "소고기하이라이스"
    if name in ("차돌된장찌개", "차돌 된장찌개"):
        name = "차돌박이된장찌개"
    if name in ("황태구이_양념", "황태구이 양념"):
        name = "북어구이(고추장)"
    if name in ("치즈돈가스", "고구마치즈돈가스"):
        name = name.replace("돈가스", "돈까스")
    if name == "양파링":
        name = "어니언링"
    result = _from_custom_recipe(name, weight_g)
    if result is None:
        result = _from_external_recipe(name, weight_g)
    if result is None:
        result = _try_cascade(name, weight_g)
    if result is None:
        for prefix in MENUGEN_MODIFIER_PREFIXES:
            if name.startswith(prefix) and len(name) > len(prefix):
                result = _try_cascade(name[len(prefix):], weight_g)
                if result is not None:
                    break
    if result is None:
        return {"matched": False, "units": {g: 0.0 for g in EXCHANGE_GROUPS}, "source": None,
                "unresolved_ingredients": []}
    return {"matched": True, **result}


if __name__ == "__main__":
    for test_name, test_w in [("김치찌개", 790), ("제육볶음", 150), ("쌀밥", 275), ("사과", 100)]:
        r = compute_exchange_units(test_name, test_w)
        print(test_name, test_w, "g ->", r["matched"], r["source"],
              {k: round(v, 2) for k, v in r["units"].items()})
