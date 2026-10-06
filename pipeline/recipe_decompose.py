# -*- coding: utf-8 -*-
"""1.7단계: 레시피DB 재료 분해 -> db104(원재료, 조리상태별) 매칭 -> 비율 합산.
food_db(1단계)/gagong_db(1.5단계)에서 메뉴 전체가 매칭 안 될 때 쓰는 최후 수단 중 하나.
"""
import sys, os, json, re, statistics
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ingredient_parser import parse_ingredients

with open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'recipe_db_full.json'), encoding="utf-8") as f:
    RECIPE = json.load(f)
RECIPE_BY_NAME = {}
for r in RECIPE:
    RECIPE_BY_NAME.setdefault(r["name"], r)

with open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'db104_raw_ingredients.json'), encoding="utf-8") as f:
    DB104 = json.load(f)

DB104_MAP = {"kcal": "에너지", "protein": "단백질", "fat": "지방", "carb": "탄수화물", "sugar": "당류",
             "fiber": "총 식이섬유", "ca": "칼슘", "fe": "철", "vitA": "비타민 A", "vitC": "비타민 C",
             "satFat": "총 포화지방산", "na": "나트륨"}
NUT_FIELDS = list(DB104_MAP.keys())

# 조리법(RCP_WAY2) -> db104 조리상태 표기 우선순위(앞에서부터 시도)
# db104에 실제 존재하는 상태 표기 27종을 전수조사해서 반영함(2026-09-20 수정: '데친것'/'조리후' 누락 발견 후 보강)
WAY_TO_STATE = {
    "찌기": ["찐것", "데친것", "삶은것", "조리후", "생것"],
    "삶기": ["삶은것", "데친것", "조리후", "생것"],
    "끓이기": ["끓인것", "삶은것", "데친것", "조리후", "생것"],
    "볶기": ["볶은것", "구운것", "조리후", "생것"],
    "볶음": ["볶은것", "구운것", "조리후", "생것"],
    "굽기": ["구운것", "조리후", "생것"],
    "튀기기": ["튀긴것", "조리후", "구운것", "생것"],
    "무침": ["데친것", "생것", "삶은것"],
    "절임": ["소금에 절여 말린것", "생것"],
    "기타": ["조리후", "생것"],
}
# 마지막 안전망: 위 리스트에도 없으면 이 순서로 한 번 더 시도(조리후가 생것보다 실제 배식 상태에 가까움)
DEFAULT_STATE_ORDER = ["조리후", "생것"]


# 레시피DB 재료명 표기가 db104 재료명 표기와 다른 흔한 동의어들
# (레시피DB 표기 -> db104 표기). 발견되는 대로 계속 추가할 것.
SYNONYMS = {
    "계란": "달걀",
    "대파": "파",
    "실파": "파",
    # 2026-09-27 수정: "고추"로만 리다이렉트하면 후보가 8개(빨간색/초록색/말린것/풋고추 등)나
    # 걸려서 조리상태 우선순위 로직이 원하는 품종이 아니라 목록에서 먼저 나온 아무 "생것"이나
    # 집어감(실제로 풋고추가 엉뚱하게 85kcal짜리 "고추, 빨간색, 생것"으로 잘못 매칭됐던 버그).
    # "밀가루"와 동일한 방식으로 db104 표기 전체를 정확히 지정해서 고침.
    "청양고추": "고추, 청양고추, 생것",
    "홍고추": "고추",  # db104에 "홍고추" 전용 표기가 없어 부득이 유지 - "빨간색" 계열 중 어느
                      # 걸 골라도 확정적이지 않음. 필요시 확인 후 특정 표기로 재지정할 것.
    "풋고추": "고추, 풋고추, 생것",
    "식용유": "혼합식물성유",  # db104에 '식용유' 단독 항목이 없어 '혼합식물성유'(시판 식용유와 가장 유사)로 근사
    "쌀": "멥쌀",  # db104는 '쌀' 단독 표기가 없고 '멥쌀, 백미, ...'로만 존재
    "숙주": "숙주나물",
    # 2026-09-27 추가: find_db104_candidates가 콤마 앞 "첫 토큰"만 정확히 비교하는 구조라,
    # db104 표기의 첫 토큰이 레시피 재료명과 다르면(예: "스파게티면" vs "스파게티") 후보를
    # 아예 못 찾는다. "조개크림파스타" 레시피 분해 점검 중 발견.
    "스파게티": "스파게티면",  # db104엔 "스파게티"가 아니라 "스파게티면, 말린것, 삶은것"으로 존재
    "올리브오일": "올리브유",
    "양송이": "양송이버섯",
    "생크림": "크림",  # db104엔 "크림, 생크림"으로 존재(첫 토큰이 "크림")
    "밀가루": "밀, 중력밀가루",  # db104는 "밀, 강력/박력/중력/통밀가루" 여러 하위 품목이 전부
                              # 첫 토큰 "밀"을 공유해서(생것/도정 등 곡물 자체까지 포함) 콤마
                              # 포함 동의어로 전체 표기를 정확히 지정(일반 요리용 중력분 선택)
    "파슬리가루": "파슬리",  # db104엔 "가루" 표기 없이 "파슬리, 생것/말린것"만 존재
    "소고기사태": "소고기, 수입산, 사태, 끓인것",  # 사용자 지정(소고기우거지해장국)
}


def _norm(s):
    if not s:
        return ""
    s = re.sub(r"[\(（].*?[\)）]", "", s)
    return s.replace(" ", "").strip()


def find_db104_candidates(ingredient_name):
    """db104에서 재료명으로 후보를 찾는다. '이름, 상태1, 상태2' 형식이므로
    콤마 앞부분(첫 토큰)이 재료명과 일치하는 레코드를 후보로 삼는다.
    동의어 사전에 있으면 "직접 일치보다 동의어를 우선"한다(2026-09-27 수정: 예전엔
    직접 일치가 하나라도 있으면 동의어를 아예 안 써서, "스파게티"가 이미 엉뚱한
    "스파게티, 미트소스 스파게티, 냉동" 냉동식품에 걸려있으면 동의어 "스파게티면"으로
    바로잡을 방법이 없었음 - 동의어를 등록했다는 건 직접 일치가 틀렸거나 없다는 뜻이므로
    항상 동의어를 우선시킴).
    동의어에 콤마가 있으면(예: "밀, 중력밀가루") db104 표기 전체와 정확히 일치하는 것만
    찾는다 - "밀가루"처럼 여러 하위 품목이 같은 첫 토큰("밀")을 공유해서 첫 토큰만으로는
    원하는 하위 품목을 못 고르는 경우에 씀."""
    q = _norm(ingredient_name)
    out = []
    for r in DB104:
        base = _norm(r["식품명"].split(",")[0])
        if base == q:
            out.append(r)
    used_synonym = None
    if ingredient_name in SYNONYMS:
        alt = SYNONYMS[ingredient_name]
        alt_out = []
        if "," in alt:
            q2_full = _norm(alt)
            for r in DB104:
                if _norm(r["식품명"]) == q2_full:
                    alt_out.append(r)
        else:
            q2 = _norm(alt)
            for r in DB104:
                base = _norm(r["식품명"].split(",")[0])
                if base == q2:
                    alt_out.append(r)
        if alt_out:
            out = alt_out
            used_synonym = alt
    return out, used_synonym


def pick_db104_state(candidates, cooking_way):
    """조리법에 맞는 상태를 우선순위대로 찾고, 없으면 생것 -> '가장 단순한 표기'(콤마 segment 수가 가장 적은 것) 순으로 대체.
    예: 소금 검색 시 '소금,정제염'(2단계)을 '소금,가공염,맛소금'(3단계, 특수품)보다 우선.
    2026-09-21 수정: "쌀"->"멥쌀" 동의어로 검색하면 "멥쌀, 쌀눈, 볶은것"(쌀겨/쌀눈 부산물,
    일반 쌀과 영양성분이 전혀 다름)이 "볶기" 조리법의 "볶은것" 키워드에 우연히 걸려 잘못
    선택되는 버그가 있었다 - 일반적으로 "쌀눈"은 "쌀"의 일반적 의미가 아니므로 다른 후보가
    있으면 항상 배제한다."""
    if not candidates:
        return None, None
    normal = [c for c in candidates if "쌀눈" not in c["식품명"]]
    candidates = normal if normal else candidates
    state_order = WAY_TO_STATE.get(cooking_way, DEFAULT_STATE_ORDER)
    for state in state_order + ["생것"]:
        for c in candidates:
            if state in c["식품명"]:
                return c, state
    for c in candidates:
        if "," not in c["식품명"]:
            return c, "(상태구분없음)"
    plainest = sorted(candidates, key=lambda c: (c["식품명"].count(","), len(c["식품명"])))[0]
    return plainest, "(대체:가장단순한표기)"


def match_ingredient_to_db104(name, cooking_way):
    cands, used_synonym = find_db104_candidates(name)
    if not cands:
        return None
    picked, state = pick_db104_state(cands, cooking_way)
    return {"record": picked, "state_used": state, "n_candidates": len(cands), "used_synonym": used_synonym}


def decompose_recipe(recipe_name, cooking_way=None, verbose_log=None):
    """레시피명으로 recipe_db를 찾아 재료를 파싱하고 db104에 매칭, 비율 합산.
    반환: {
      "recipe_name", "found": bool,
      "total_parsed_weight_g": float,   # 매칭 성공한 재료들의 g 합
      "contrib_per_total": {필드: 절대값(매칭성공 재료 총합 기준, per 100g 아님)},
      "matched_ingredients": [...], "unmatched_ingredients": [...],
      "excluded_no_weight": [...], "excluded_vague": [...],
    }
    """
    r = RECIPE_BY_NAME.get(recipe_name)
    if r is None:
        return {"recipe_name": recipe_name, "found": False}
    way = cooking_way or r.get("way")
    parsed = parse_ingredients(r["ingredients"])

    total_weight = 0.0
    contrib = {f: 0.0 for f in NUT_FIELDS}
    matched, unmatched = [], []

    for ing in parsed["items"]:
        m = match_ingredient_to_db104(ing["name"], way)
        if m is None:
            unmatched.append(ing)
            continue
        rec = m["record"]
        amt = ing["amount_g"]
        total_weight += amt
        for f, col in DB104_MAP.items():
            v = rec.get(col)
            if v not in (None, "", "-", "Tr", "tr"):
                try:
                    contrib[f] += float(v) * amt / 100.0
                except ValueError:
                    pass
        matched.append({**ing, "db104_name": rec["식품명"], "state_used": m["state_used"], "n_candidates": m["n_candidates"], "used_synonym": m["used_synonym"]})

    return {
        "recipe_name": recipe_name, "found": True, "cooking_way": way,
        "total_parsed_weight_g": round(total_weight, 2),
        "contrib_per_total": {k: round(v, 3) for k, v in contrib.items()},
        "matched_ingredients": matched, "unmatched_ingredients": unmatched,
        "excluded_no_weight": parsed["excluded_no_weight"], "excluded_vague": parsed["excluded_vague"],
        "recipe_db_weight_field": r.get("weight"),
    }


if __name__ == "__main__":
    import sys as _sys
    name = _sys.argv[1] if len(_sys.argv) > 1 else "삼색계란찜"
    result = decompose_recipe(name)
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "_debug_decompose_test.json"), "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    print("done")
