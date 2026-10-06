# -*- coding: utf-8 -*-
"""메뉴 항목 하나를 food_db(1) -> gagong_db(1.5) -> recipe_db 재료분해/db104(1.7) 순으로 자동매칭.
성공하면 {"source","name","per100":{...12개필드...}, "detail":{...}} 반환, 실패하면 None."""
import sys, os, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from food_search import load_db as load_food, search as search_food, PRI_RANK
from gagong_search import load_db as load_gagong, search as search_gagong
from recipe_decompose import decompose_recipe, RECIPE_BY_NAME, find_db104_candidates, pick_db104_state, DB104_MAP

FOOD_DB = load_food()
GAGONG_DB = load_gagong()

NUT_FIELDS = ["kcal", "protein", "fat", "carb", "sugar", "fiber", "ca", "fe", "vitA", "vitC", "satFat", "na"]


# food_db 표기가 실제 메뉴판 표기와 다른 흔한 동의어 (메뉴판 표기 -> food_db 표기)
FOOD_DB_SYNONYMS = {
    "포기김치": "배추김치",
    "돈까스": "돈가스",
    "치킨까스": "치킨가스",
    "생선까스": "생선까스",  # 이미 동일, 확인용
    "미소국": "미소된장국",
    "대패삼겹살": "삼겹살구이",  # 대패=얇게 썬 것일 뿐 영양성분은 삼겹살구이와 사실상 동일
    "삼겹살": "삼겹살구이",
    "볼어묵볶음": "어묵볶음",
    "후리가케밥": "쌀밥",
    "돈육고추장찌개": "돼지고기찌개_간편조리세트_돼지고기고추장찌개",
    "햄고추장찌개": "고추장찌개_두부",  # 햄 전용 항목은 없어 단백질원 미지정 버전으로 대체
    "호박양파볶음": "애호박볶음",
    "데리야끼삼치구이": "삼치구이",
    "쫄깃단무지무침": "단무지",  # 사용자 지정: 무침(단무지무침)이 아니라 단무지 자체로 매칭
    "산고추지": "고추장아찌",  # 사용자 지정: 꽈리고추장아찌로 추정 - 꽈리고추 단독 장아찌는 DB에 없어 일반 고추장아찌로 대체
    "장칼국수": "칼국수",  # gagong_db "장칼국수"는 건면+육수+다대기로 나뉜 간편조리세트(밀키트) 기준이라
                          # 완성품 기준인 food_db "칼국수"(재료량 기반 산출)로 먼저 매칭되게 우회
    # 2026-09-27 추가: try_food_db()는 정확히 일치하는 이름만 보고(부분일치 후보는 안 씀,
    # 이유는 아래 참고) food_db에 원하는 항목이 있어도 표기가 살짝 다르면 못 찾고 gagong_db로
    # 새 나가는 경우들 - food_db의 실제 표기 그대로 지정해서 우선순위를 되돌림.
    # food_db엔 "순두부찌개_해물/모듬/김치/간편조리세트_*"만 있고 정확히 "순두부찌개"인 항목이
    # 없음. 2026-09-27: 사용자가 원래 지목한 "순두부찌개_간편조리세트_우삼겹 순두부찌개"(47kcal)로
    # 지정(처음에 임의로 "_모듬"(25kcal)을 썼다가 사용자 확인 후 정정).
    "순두부찌개": "순두부찌개_간편조리세트_우삼겹 순두부찌개",
    "메추리알조림": "메추리알장조림",  # food_db엔 "메추리알장조림"으로만 있음("조림"과 "장조림"은 다른 표기)
    "치킨너겟": "닭튀김_New치킨너겟",
    "닭갈비": "닭볶음(닭갈비)_매운양념",  # gagong_db "닭갈비"(163.5kcal, 미량영양소 결측)보다
                                        # food_db 이 항목이 fiber/ca/fe/vitA/vitC까지 다 있어서 우선
}


# 2026-09-21: food_db 뿐 아니라 gagong_db/recipe_db 등 매칭 파이프라인 전체 진입 전에
# 이름 자체를 바꿔치기하는 동의어. "이화수육개장"→"육개장"처럼 수식어를 뗀 이름이 food_db엔
# 없고 gagong_db에만 있는 경우가 많아 food_db 전용인 FOOD_DB_SYNONYMS로는 부족해서 따로 둠.
GENERAL_SYNONYMS = {
    # 2026-10-06 추가: 8/25 401 사진 확인 - 버터(BUTTER FRESH)와 세트로 나온 작은 잼 패키지,
    # 크루아상에 가려져 라벨은 안 보이지만 색상(투명 주황/호박색)이 살구잼에 가까워 이걸로 매칭.
    "잼": "살구잼",
    "이화수육개장": "육개장",
    "돈육김치찌개": "김치찌개",
    "몽글순두부찌개": "순두부찌개_해물",  # 사용자 지정: "몽글" 떼고 food_db "순두부찌개_해물"로 직접 매칭
                                        # (일반 "순두부찌개"로 보내면 FOOD_DB_SYNONYMS가 다른 변형으로 리다이렉트해서 우회)
    "전골떡볶이": "떡볶이",
    "돈등뼈감자탕": "감자탕",
    "왕돈가스": "등심돈가스",  # "왕"을 뗀 일반 규칙보다 우선 적용되는 명시적 예외
    "목살김치찌개": "김치찌개",
    "황제해물짬뽕": "해물짬뽕",
    "고구마닭갈비": "닭갈비",
    "크랩알밥": "알밥",
    "왕떡만두국": "떡만두국",
    "옹심이": "찹쌀옹심이",
    # 2026-09-27 추가
    "초장": "초고추장",  # gagong_db에 "초장" 단독은 없고 "초고추장"으로만 존재
    "타르소스": "타르타르소스",  # gagong_db에 "타르소스" 단독은 없고 "타르타르소스"로만 존재
    "설탕꽈배기": "꽈배기",
    "오그락지무침": "무말랭이무침",  # 오그락지=무말랭이의 방언 표기
    "손만두": "만두",
    "상추쌈": "상추",  # db104 직접매칭 대상 - "상추쌈"은 첫 토큰이 안 맞아 "상추"로 정규화
    "돼지고기육전": "육전",  # "돼지고기"(생고기) 대신 실제 조리된 "육전"으로
    "메쉬드포테이토": "매쉬드포테이토",  # 표기 오차, gagong_db엔 "매쉬드포테이토"로만 존재
    "청포묵김무침": "탕평채",  # 청포묵+고기+채소+김을 무친 전통 요리 = 탕평채, food_db에 정확히 있음
    # "간장마늘지"/"숯불간장불고기"는 GENERAL_SYNONYMS가 아니라 build_month.py의
    # DECOMPOSE_OVERRIDES에 등록(아래 참고) - 이름에 "간장"이 들어있어 _special_weight()의
    # SAUCE_KEYWORDS 판정("간장")에 먼저 걸려서 9g 소스로 잘못 처리되는 문제가 있었음
    # (GENERAL_SYNONYMS는 auto_match() 내부에서만 적용되고 build_month의 중량 판정보다 늦게 적용됨).
    # 2026-09-27: 아래는 "수식어+기본요리" 결합형 표기라 수식어를 떼고 기본요리명으로 매칭.
    # (수식어 자체가 별도 실재료가 아니라 브랜드명/조리스타일/식감 표현 등이라 단순 접두어 제거로 충분)
    "강된장열무비빔밥": "열무비빔밥", "맑은홍합탕": "홍합탕", "맛살부추전": "부추전",
    "맛초킹탕수육": "탕수육", "명란떡갈비": "떡갈비", "미니쌀국수": "쌀국수", "미니우동": "우동",
    "미니짬뽕": "짬뽕", "사각어묵볶음": "어묵볶음", "새우젓호박볶음": "호박볶음",
    "호박새우젓볶음": "호박볶음", "아삭이고추무침": "고추무침", "야채쫄면": "쫄면",
    "야채필라프": "필라프", "옥수수콘샐러드": "콘샐러드", "왕만두찜": "왕만두",
    "칠리핫도그": "핫도그", "팽이미역줄기볶음": "미역줄기볶음", "후르츠탕수육": "탕수육",
    "냉짬뽕": "짬뽕", "오복지무침": "오복지", "우엉채볶음": "우엉채",
    "쥐어채볶음": "쥐어채", "오징어링튀김": "오징어링", "청경채겉절이": "겉절이",
    "브로콜리초회": "브로콜리", "김말이강정": "김말이", "고기산적조림": "고기산적",
    "유부우동국": "유부우동",
    # 2026-09-27: 국물류인데 DB에 없어 기존 우동국물 캐시(가공식품 농축액 1:10 희석 보정값)로 대체
    "유부장국": "우동국물", "팽이우동국": "우동국물", "팽이장국": "우동국물",
    "양파간장": "간장",  # "양파간장"(양파 넣은 간장 양념) 자체는 DB에 없어 베이스인 간장으로 대체.
                        # 9g만 쓰니 오차는 미미함(0.8kcal 수준).
    "김밥볶음밥": "볶음밥",  # 사용자 지시로 50:50 분해 대신 그냥 볶음밥 하나로 단순화
    "봉골레파스타": "조개크림파스타",  # recipe_db에 정확히 있는 레시피로 매칭
    "스크램블에그": "계란후라이",
    "뚝)된장찌개": "된장찌개",  # "뚝)"="뚝배기" 줄임 표기
    "뚝)청국장찌개": "청국장찌개",
    "트러플풍기파스타": "표고크림파스타",  # 사용자 지정: recipe_db에 있는 가장 유사한 레시피로 대체
    "무무침": "무생채",  # food_db에 "무무침"은 없고 "무생채"로 존재
    "적양배추": "양배추",  # "적양배추" 전용 표기 없어 일반 양배추로 대체(영양성분 거의 동일)
    "쪽파": "파",  # db104에 "쪽파" 전용 표기 없어 일반 파로 대체
    "뚝배기소불고기": "소불고기",  # 사용자 지정: "뚝배기" 조리용기 표현 떼고 매칭
    "생선가스": "생선까스",  # 표기 차이("가스"/"까스") - food_db엔 "까스"로만 존재
    "쌈채소": "상추",  # 사용자 지정
    "가마보꼬어묵조림": "어묵조림",  # 사용자 지정
    "고추양파무침": "양파장아찌",  # 사용자 지정
    "데리야끼동그랑조림": "동그랑땡전",  # 사용자 지정
    "떡고기산적조림": "떡갈비",  # 사용자 지정
    "냄비우동": "우동",  # 사용자 지정
    "돈육강정": "탕수육",  # 사용자 지정
    "딤섬": "삼색딤섬",  # 사용자 지정: recipe_db에 있는 레시피로 대체
    "보쌈정식": "보쌈",  # 사용자 지정
    "제육김치볶음": "제육볶음",  # 사용자 지정
    "피쉬볼볶음": "어묵조림",  # 사용자 지정
    "참치야채비빔밥": "비빔밥_참치_양념장",  # 사용자 지정
    "바지락칼국수": "칼국수_바지락",  # 사용자 지정: food_db로 대체(기존 gagong_db 중앙값 보정 대신)
    "오그락지": "무말랭이무침",  # 사용자 지정: "오그락지무침"뿐 아니라 "오그락지"(무침 없는 표기)도 동일 처리
}

# 사용자 지정 일반 규칙: 이 접두어가 붙은 이름이 그대로는 안 잡히면 접두어를 떼고 재시도.
# "왕돈가스"처럼 GENERAL_SYNONYMS에 명시적 예외가 있으면 그게 먼저 적용되고 이 규칙까지
# 안 옴(왕돈가스=등심돈가스이지 그냥 돈가스가 아니라서).
PREFIX_STRIP_RULES = ["돈육", "왕"]


def try_food_db(name):
    exact, _ = search_food(FOOD_DB, name, limit=5)
    used_synonym = None
    if not exact and name in FOOD_DB_SYNONYMS:
        exact, _ = search_food(FOOD_DB, FOOD_DB_SYNONYMS[name], limit=5)
        used_synonym = FOOD_DB_SYNONYMS[name] if exact else None
    if not exact:
        return None
    d = exact[0]  # 이미 PRIORITY 순 정렬됨
    n = d["n"]
    per100 = {f: n.get(f) for f in NUT_FIELDS}
    out = {"source": "food_db", "name": d["name"], "origin": d["origin"], "per100": per100}
    if used_synonym:
        out["used_synonym"] = used_synonym
    return out


def try_gagong_db(name):
    exact, _ = search_gagong(GAGONG_DB, name, limit=100)
    if not exact:
        return None
    fmap = {"kcal": "에너지(kcal)", "protein": "단백질(g)", "fiber": "식이섬유(g)", "ca": "칼슘(mg)",
            "fe": "철(mg)", "vitA": "비타민 A(μg RAE)", "vitC": "비타민 C(mg)", "satFat": "포화지방산(g)",
            "sugar": "당류(g)", "na": "나트륨(mg)", "fat": "지방(g)", "carb": "탄수화물(g)"}
    import statistics
    per100 = {}
    for f, col in fmap.items():
        vals = [float(d[col]) for d in exact if d[col] not in (None, "")]
        per100[f] = round(statistics.median(vals), 2) if vals else None
    return {"source": "gagong_db", "name": exact[0]["식품명"], "n_dup": len(exact), "per100": per100,
            "_codes": [d["식품코드"] for d in exact],
            "note": "가공식품DB 중앙값(지방/탄수화물 포함, 원본 엑셀에서 합쳐넣은 CSV 기준)"}


def try_recipe_decompose(name):
    if name not in RECIPE_BY_NAME:
        return None
    result = decompose_recipe(name)
    if not result["found"] or result["total_parsed_weight_g"] <= 0:
        return None
    w = result["total_parsed_weight_g"]
    per100 = {f: round(v * 100.0 / w, 3) for f, v in result["contrib_per_total"].items()}
    return {"source": "recipe_decompose", "name": name, "per100": per100,
            "total_parsed_weight_g": w, "n_unmatched_ingredients": len(result["unmatched_ingredients"]),
            "unmatched_ingredients": [i["name"] for i in result["unmatched_ingredients"]],
            "recipe_db_reported_weight": result["recipe_db_weight_field"]}


def try_db104_direct(name):
    """메뉴명 자체가 이미 원재료인 경우(상추, 고추, 다시마 등) - food_db/gagong_db/recipe_db
    어디에도 없는 게 당연함(완성요리/가공식품/레시피가 아니라 그 자체가 생재료라서).
    db104에서 이름 그대로 찾아 상태 우선순위(생것 기본)로 하나 골라 씀.
    2026-09-27 추가: 콤마 분리 규칙("상추쌈,풋고추" 등)으로 개별 재료명이 그대로 매칭
    대상이 되는 경우가 늘면서 필요해짐."""
    cands, used_synonym = find_db104_candidates(name)
    if not cands:
        return None
    rec, state = pick_db104_state(cands, None)
    if rec is None:
        return None
    # db104는 결측값을 "-"/"Tr"/빈 문자열 등으로 표기하므로(recipe_decompose.py의 기존 처리와
    # 동일 컨벤션) 숫자로 안 바뀌는 값은 None으로 정리. 2026-09-27: 이걸 안 해서 "쪽파"(파로
    # 리다이렉트)의 sugar/fiber/satFat가 "-" 문자열로 들어가 파이프라인 전체가 죽는 버그 있었음.
    per100 = {}
    for f, col in DB104_MAP.items():
        v = rec.get(col)
        if v in (None, "", "-", "Tr", "tr"):
            per100[f] = None
        else:
            try:
                per100[f] = float(v)
            except (TypeError, ValueError):
                per100[f] = None
    out = {"source": "db104_direct", "name": rec["식품명"], "per100": per100}
    if used_synonym:
        out["used_synonym"] = used_synonym
    return out


def _try_cascade(name, prefer_db104=False):
    # 우선순위(2026-09-20 재조정): food_db -> 1.7단계(레시피DB 재료분해+db104) -> gagong_db(가공식품, 최후수단)
    # -> db104(원재료DB) 직접매칭(2026-09-27 추가, 완성요리/가공식품/레시피 어디에도 없는
    # 생재료용 최후수단). 이유: gagong_db는 식이섬유/칼슘/철/비타민A·C 결측률이 89~96%라
    # NRF6.3 점수를 왜곡하고, food_db/gagong_db엔 이름이 비슷한 엉뚱한 가공품이 우연히
    # 먼저 걸리는 경우가 있어(예: "당근"이 가공식품 200.5kcal에 먼저 걸림) 기본은 이 순서.
    #
    # 2026-09-27 추가: prefer_db104=True면 순서를 뒤집어 db104를 맨 먼저 본다.
    # build_month.py에서 DECOMPOSE_OVERRIDES로 "재료 단위"까지 손으로 쪼갠 이름(당근/소고기사태
    # 등 진짜 생재료)에 한해 이 플래그를 쓴다 - 이런 이름은 애초에 db104에만 존재하는 게
    # 정상이라 먼저 봐도 안전하고(완성요리/가공품 이름은 db104에 아예 없어서 그냥 통과됨),
    # food_db/gagong_db의 우연한 오매칭을 원천 차단할 수 있다.
    steps = [try_food_db, try_recipe_decompose, try_gagong_db, try_db104_direct]
    if prefer_db104:
        steps = [try_db104_direct, try_food_db, try_recipe_decompose, try_gagong_db]
    for step in steps:
        r = step(name)
        if r:
            return r
    return None


def auto_match(name, prefer_db104=False):
    name = GENERAL_SYNONYMS.get(name, name)
    r = _try_cascade(name, prefer_db104)
    if r:
        return r
    for prefix in PREFIX_STRIP_RULES:
        if name.startswith(prefix) and len(name) > len(prefix):
            r = _try_cascade(name[len(prefix):], prefer_db104)
            if r:
                return r
    return None


if __name__ == "__main__":
    import sys as _sys
    names = _sys.argv[1:]
    out = {}
    for n in names:
        out[n] = auto_match(n)
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "_debug_auto_match_test.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print("done")
