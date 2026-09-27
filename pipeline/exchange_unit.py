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
    group = FOOD_GROUP_MAP.get(raw_group_name)
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
    dish = _lookup_menugen(name)
    if dish is None:
        return None
    ingredients = dish.get("ingredients") or []
    if not ingredients:
        return None
    try:
        ref_weight = float(dish.get("weight_g") or 0)
    except (TypeError, ValueError):
        ref_weight = 0
    scale = (target_weight_g / ref_weight) if ref_weight > 0 else 1.0

    units = {g: 0.0 for g in EXCHANGE_GROUPS}
    any_used = False
    unresolved = []
    for ing in ingredients:
        try:
            w = float(ing.get("weight_g") or 0) * scale
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
    if not items:
        return None
    ref_weight = sum(it["amount_g"] for it in items)
    scale = (target_weight_g / ref_weight) if ref_weight > 0 else 1.0

    units = {g: 0.0 for g in EXCHANGE_GROUPS}
    any_used = False
    unresolved = []
    for ing in items:
        m = match_ingredient_to_db104(ing["name"], r.get("way"))
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


def _try_cascade(name, weight_g):
    result = _from_menugen(name, weight_g)
    if result is None:
        result = _from_recipe_db(name, weight_g)
    if result is None:
        result = _from_direct_db104(name, weight_g)
    return result


def compute_exchange_units(name, weight_g):
    """메뉴 항목 하나(원자 단위 이름) + 이미 산정된 중량(g)으로 6개 식품군 교환단위 계산.
    MenuGen -> recipe_db -> db104 직접매칭 순으로 시도. 다 실패하면 승인된 수식어 접두어를
    떼고 기본요리명으로 한 번 더 시도. 그래도 실패하면 matched=False."""
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
