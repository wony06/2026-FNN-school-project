# -*- coding: utf-8 -*-
import json, re, os, sys

PIPELINE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(PIPELINE_DIR)
sys.path.insert(0, PIPELINE_DIR)
from exchange_unit import compute_exchange_units, EXCHANGE_GROUPS

NUT_FIELDS = ["kcal", "protein", "fat", "carb", "sugar", "fiber", "ca", "fe", "vitA", "vitC", "satFat", "na"]

SELF_KEYWORDS = {
    "샐러드&토핑&드레싱", "즉석라면", "계란후라이", "즉석꼬치어묵", "self계란후라이",
    "즉석라면&계란후라이", "토스트&버터,잼", "한강라면&계란후라이", "토스트&버터,잠",
}

# 2026-09-21: SELF 코너와는 다르지만("실제로 있긴 함") 사용자가 확인 결과 매번 나오는 게
# 아니라 선택적으로 나오는 품목이라 영양 계산에서 아예 제외하기로 함(204 마카로니과자,
# 밥 추가주문 옵션인 "추가밥").
# 2026-09-27 추가: "한마리"는 같은 트레이의 메인(예: 조기구이)이 "1마리 통째로" 나간다는
# 수량 표기가 사이드 줄에 잘못 분리된 것일 뿐 실제 별도 음식이 아니라 제외. "뿌링클가루"는
# 사용자 지시로 영양 계산에서 제외(치킨 시즈닝 가루, 소량이라 무시).
OPTIONAL_EXCLUDE_KEYWORDS = {"마카로니과자", "추가밥", "한마리", "뿌링클가루"}


def is_self_or_junk(tok):
    if not tok:
        return True
    if tok in SELF_KEYWORDS:
        return True
    if tok in OPTIONAL_EXCLUDE_KEYWORDS:
        return True
    if "self" in tok.lower():
        return True
    if not re.search(r"[가-힣a-zA-Z0-9]", tok):  # 순수 기호(&, / 등)만 있는 토큰
        return True
    return False

RICE_WORDS = ("쌀밥", "흑미밥", "백미밥", "잡곡밥", "현미밥", "추가밥", "잡곡밥/현미밥")
SOUP_HINTS = ("국", "탕", "찌개", "전골", "국물")

def classify_main_weight(name):
    if any(w in name for w in ("찌개", "전골", "탕", "해장국", "국밥")) and "볶음" not in name:
        return 300, "찌개/탕류 - 표준 300g"
    if any(w in name for w in ("면", "국수", "파스타", "우동", "라면", "스파게티", "냉모밀", "냉우동")):
        return 300, "면류 - 표준 300g"
    if any(w in name for w in ("덮밥", "비빔밥", "볶음밥", "동", "솥밥", "오므라이스", "필라프", "카레라이스", "알밥")):
        return 250, "밥類 단일메뉴 - 표준 250g(별도 분해 안함)"
    return 150, "일반 메인반찬 - 표준 150g"

def classify_side_weight(name):
    if name in RICE_WORDS or name.replace("/", "") in ("잡곡밥현미밥",):
        return 190, "밥 - 표준 190g"
    if any(name.endswith(w) or w in name for w in SOUP_HINTS) and len(name) <= 8:
        return 200, "국/탕류 사이드 - 표준 200g"
    return 40, "일반 반찬 - 표준 40g"


# 2026-09-21: 105(학생식당) 실측 그릇 치수 기반 표준중량. 401/204는 아직 실측이 없어
# 기존 classify_main_weight/classify_side_weight(추정치)를 그대로 씀 - 105만 교체.
# 부피는 절두원뿔 공식 V=(πh/3)(R²+Rr+r²)로 계산, 사진으로 충전율을 눈대중 확인,
# 재료별 밀도(국물류1.0 / 밥0.65 / 반찬·덮밥토핑0.75 g/mL)를 곱해 무게 환산.
#   즉석 검정냄비: 윗18.5·밑10·높6cm -> 985mL, 78% 충전 -> 약 770mL x 1.0 = 약 790g
#     (찌개·면류 둘 다 이 냄비를 그대로 씀 - 사진으로 확인)
#   즉석 밥그릇: 윗10.5·밑7.5·높6cm -> 385mL, 고봉 110% -> 약 424mL x 0.65 = 약 275g
#   한식 덮밥그릇: 윗19·밑11·높6.5cm -> 1176mL, 65% 충전 -> 약 764mL x 0.75 = 약 570g
#   공통 반찬그릇: 4.5x4.5x0.7cm(그릇 자체는 얕음, 고봉 담김 반영 별도 추정) -> 약 34g
# 양식은 사용자 지시로 기존 표준 유지(재계산 안 함).
BOWL_WEIGHT_105_JEUKSEOK_MAIN = 790  # 즉석: 찌개/면 공통(검정냄비)
BOWL_WEIGHT_105_HANSIK_MAIN = 570    # 한식: 덮밥류(덮밥그릇)
BOWL_WEIGHT_105_RICE_SIDE = 275      # 즉석 밥그릇(별도로 밥이 나오는 경우)
BOWL_WEIGHT_105_BANCHAN = 34         # 공통 반찬그릇(카테고리 무관)


def classify_main_weight_105(category, name):
    if category == "즉석":
        if name == "순살닭한마리":
            return BOWL_WEIGHT_105_JEUKSEOK_MAIN, "105 즉석 동일 냄비 기준 표준 추정 790g"
        is_stew = any(w in name for w in ("찌개", "전골", "탕", "해장국", "국밥")) and "볶음" not in name
        is_noodle = any(w in name for w in ("면", "국수", "파스타", "우동", "라면", "스파게티", "냉모밀", "냉우동"))
        if is_stew or is_noodle:
            return BOWL_WEIGHT_105_JEUKSEOK_MAIN, "105 즉석 검정냄비 실측(18.5/10/6cm) 기준 표준 790g"
    if category == "한식":
        if name in ("비프하이라이스", "비프 하이라이스"):
            return BOWL_WEIGHT_105_HANSIK_MAIN, "105 한식 덮밥그릇 동일 확인(사용자) - 표준 추정 570g"
        if any(w in name for w in ("덮밥", "비빔밥", "볶음밥", "동", "솥밥", "오므라이스", "필라프", "카레라이스", "알밥")):
            return BOWL_WEIGHT_105_HANSIK_MAIN, "105 한식 덮밥그릇 실측(19/11/6.5cm) 기준 표준 570g"
    return classify_main_weight(name)


def classify_side_weight_105(category, name):
    if name in ("어니언링", "양파링"):
        return 60, "[사진중량추정] 3개 × 20g = 60g(실측 아님)"
    if category == "즉석" and (name in RICE_WORDS or name.replace("/", "") in ("잡곡밥현미밥",)):
        return BOWL_WEIGHT_105_RICE_SIDE, "105 즉석 밥그릇 실측(10.5/7.5/6cm) 기준 표준 275g"
    if name in RICE_WORDS or name.replace("/", "") in ("잡곡밥현미밥",):
        return classify_side_weight(name)  # 양식 등 미실측 카테고리는 기존값 유지
    if any(name.endswith(w) or w in name for w in SOUP_HINTS) and len(name) <= 8:
        return classify_side_weight(name)  # 국물 사이드는 별도 실측 없음, 기존값 유지
    return BOWL_WEIGHT_105_BANCHAN, "105 공통 반찬그릇 실측(4.5x4.5x0.7cm) 기준 표준 34g"


# 2026-10-06: 401(생활과학관식당) 실측 그릇 치수 기반 표준중량. 105와 동일한 절두원뿔 공식
# V=(πh/3)(R²+Rr+r²)(지름만 주어진 접시류는 원기둥 V=πr²h)로 부피 계산, 사진으로 충전율을
# 눈대중 확인, 105와 동일한 재료별 밀도(국물류1.0 / 밥0.65 / 반찬·전·샐러드0.75 g/mL)를 곱해
# 무게 환산. 204는 아직 실측이 없어 기존 classify_main_weight/classify_side_weight 그대로 씀.
#   전골그릇: 윗14·밑6.5·높10cm -> 862mL, 78%(105 즉석냄비와 동일 충전율 적용) 충전
#     -> 약 672mL x 1.0 = 약 670g (나주곰탕/놀부부대찌개/전골류 등 찌개·탕 메인에 적용)
#   흰색 밥그릇: 윗13·높6·아래6cm -> 445mL, 고봉 110% -> 약 489mL x 0.65 = 약 320g
#   놋그릇 밥그릇: 윗11·아래11(사용자 확인: 위아래 거의 동일)·높5cm -> 475mL, 고봉 110%
#     -> 약 523mL x 0.65 = 약 340g (실제 트레이 사진에서 흰 밥그릇만 확인돼 기본값은 흰색 채택,
#     놋그릇 밥그릇 사용이 확인되면 이 값으로 교체 가능하도록 상수만 별도 보관)
#   흰색 단무지 접시그릇: 지름9·높1.5cm(사용자 지정) -> 95mL, 90% 충전
#     -> 약 86mL x 0.75 = 약 64g (일반 반찬 기본값)
#   흰색 소스그릇(초록띠): 윗9.5·밑6.5·높5.5cm -> 280mL, 60% 충전 -> 약 168mL x 1.0 = 약 168g
#     (2026-10-06 사용자 확인: 실제로 소스/양념장류와 우동국 계열에 쓰는 그릇. 미역국 등
#     다른 국/탕류는 밥그릇보다 큰 별도 그릇이라 이 값으로 매칭하면 안 됨 - 아직 미실측이라
#     해당 항목은 기존 classify_side_weight() 추정치(200g)로 유지)
#   흰색 김치전 접시그릇: 지름13·높1.5cm(사용자 지정) -> 199mL, 85% 충전
#     -> 약 169mL x 0.75 = 약 127g (동그랑땡전/부추전/2종전 등 "전"류 사이드에 적용)
#   놋그릇 김치전 그릇: 윗14.5·아래14.5(사용자 확인: 위아래 거의 동일)·높1.5cm(사용자 지정)
#     -> 248mL, 85% 충전 -> 약 210mL x 0.75 = 약 158g (현재 미사용, 필요시 전용 상수로 보관)
#   놋그릇 김치그릇: 지름8·높1.5cm(사용자 지정) -> 75mL, 85% 충전
#     -> 약 64mL x 0.75 = 약 48g (포기김치 등 김치류 사이드에 적용)
#   하얀색 샐러드 그릇: 윗13·높6·아래6cm(흰 밥그릇과 동일 치수) -> 445mL, 70% 충전
#     -> 약 311mL x 0.75 = 약 233g ("샐러드&토핑&드레싱"은 SELF_KEYWORDS로 이미 제외돼
#     현재는 미사용, 단독 "샐러드" 표기가 나올 경우를 대비해 보관)
BOWL_WEIGHT_401_JEONGOL_MAIN = 670   # 전골그릇: 찌개/탕/전골류 메인
BOWL_WEIGHT_401_RICE_WHITE = 320     # 흰색 밥그릇
BOWL_WEIGHT_401_RICE_BRASS = 340     # 놋그릇 밥그릇(현재 미사용, 보관용)
BOWL_WEIGHT_401_BANCHAN = 64         # 흰색 단무지 접시그릇 기준 - 일반 반찬
BOWL_WEIGHT_401_SOUP_SIDE = 168      # 흰색 소스그릇 - 국/탕류 사이드로 잠정 적용
BOWL_WEIGHT_401_JEON = 127           # 흰색 김치전 접시그릇 - "전"류 사이드
BOWL_WEIGHT_401_JEON_BRASS = 158     # 놋그릇 김치전 그릇(현재 미사용, 보관용)
BOWL_WEIGHT_401_KIMCHI = 48          # 놋그릇 김치그릇 - 김치류 사이드
BOWL_WEIGHT_401_SALAD = 233          # 하얀색 샐러드 그릇(현재 미사용, 보관용)

# 2026-10-06 사용자 확인: 흰색 소스그릇은 진짜 소스/양념장류와 우동국 계열 전용 그릇.
# 미역국 등 다른 국/탕류는 밥그릇보다 큰 별도(미실측) 그릇이라 섞으면 안 됨.
SAUCE_OR_UDON_401 = {
    "소스", "양념장", "쌈장", "드레싱",
    "우동국", "우동국물", "우동장국", "유부장국", "팽이장국", "팽이우동국",
    "미소시루", "미소장국",
}


def classify_main_weight_401(category, name):
    is_stew = any(w in name for w in ("찌개", "전골", "탕", "해장국", "국밥")) and "볶음" not in name
    if is_stew:
        return BOWL_WEIGHT_401_JEONGOL_MAIN, "401 전골그릇 실측(14/6.5/10cm) 기준 표준 670g"
    return classify_main_weight(name)


def classify_side_weight_401(category, name):
    if name in RICE_WORDS or name.replace("/", "") in ("잡곡밥현미밥",):
        return BOWL_WEIGHT_401_RICE_WHITE, "401 흰색 밥그릇 실측(13/6/6cm) 기준 표준 320g"
    if "김치" in name and len(name) <= 6:
        return BOWL_WEIGHT_401_KIMCHI, "401 놋그릇 김치그릇 실측(지름8/높1.5cm) 기준 표준 48g"
    if name in SAUCE_OR_UDON_401:
        return BOWL_WEIGHT_401_SOUP_SIDE, "401 흰색 소스그릇 실측(9.5/6.5/5.5cm) 기준 소스/우동국물류 표준 168g"
    if any(name.endswith(w) or w in name for w in SOUP_HINTS) and len(name) <= 8:
        return classify_side_weight(name)  # 미역국 등 다른 국/탕류는 별도(미실측) 큰 그릇 - 기존 200g 추정 유지
    if "전" in name and len(name) <= 6:
        return BOWL_WEIGHT_401_JEON, "401 흰색 김치전 접시그릇 실측(지름13/높1.5cm) 기준 표준 127g"
    if "샐러드" in name:
        return BOWL_WEIGHT_401_SALAD, "401 하얀색 샐러드 그릇 실측(13/6/6cm) 기준 표준 233g"
    return BOWL_WEIGHT_401_BANCHAN, "401 흰색 단무지 접시그릇 실측(지름9/높1.5cm) 기준 일반 반찬 표준 64g"


# 2026-09-21: 어느 DB에도 그 이름 그대로 있는 콤보 상품이 없어 통째로 미매칭되는 메뉴/반찬은
# 예외적으로 실제 재료 단위로 쪼갠다. 메인/반찬 어느 쪽에서 나오든 같은 방식으로 적용됨.
# 케이스별로만 등록 - 새 이름이 나오면 여기 추가.
DECOMPOSE_OVERRIDES = {
    # "덮밥류는 별도 분해 안 함"이 기본 방침(classify_main_weight 참고)이지만 이 메뉴만 예외.
    # 105 한식이라 2026-09-21 그릇 실측 반영: 총량을 105 한식 덮밥그릇 표준(570g)에 맞춰
    # 기존 대패삼겹살:쌀밥 = 100:190 비율을 그대로 유지해 스케일업(100/290, 190/290 x 570).
    "대패삼겹덮밥": [
        ("대패삼겹살", 200, "대패삼겹살(덮밥 토핑) - 105 한식 덮밥그릇 실측 총량(570g) 중 비율 배분"),
        ("쌀밥", 370, "밥 - 105 한식 덮밥그릇 실측 총량(570g) 중 비율 배분"),
    ],
    # "뿌링클"은 bhc 치킨의 시즈닝 가루 브랜드명이라 그 자체로는 매칭 안 됨 - 탕수육에
    # 뿌려먹는 가루 토핑. 2026-09-27: 사용자 지시로 뿌링클가루는 영양 계산에서 제외
    # (OPTIONAL_EXCLUDE_KEYWORDS에도 등록해 단독 등장 시에도 동일하게 제외됨).
    "뿌링클탕수육": [
        ("탕수육", 40, "탕수육 - 표준 반찬 40g"),
    ],
    # 사용자 지정: 김치찌개(메인, 찌개류 표준) + 그 안에 들어간 삼겹살(반찬 함량 정도의 소량)
    # 105 즉석이라 2026-09-21 그릇 실측 반영(검정냄비 표준 790g).
    "삼겹살김치찌개": [
        ("김치찌개", 790, "105 즉석 검정냄비 실측 기준 표준 790g"),
        ("삼겹살", 40, "삼겹살(찌개 내 반찬 함량) - 표준 반찬 40g"),
    ],
    # 사용자 지정: 메추리알조림/곤약조림 둘 다 있으면 비율 나눠 합산 - 한 반찬 슬롯(40g)을 절반씩
    "메추리알곤약조림": [
        ("메추리알조림", 20, "메추리알조림 - 반찬 슬롯 절반(곤약조림과 공유) 20g"),
        ("곤약조림", 20, "곤약조림 - 반찬 슬롯 절반(메추리알조림과 공유) 20g"),
    ],
    # 사용자 지정: "만두/새우튀김 + 베이스요리" 형태소로 분해. 튀김/만두 개수는 사진에서
    # 직접 세어 unit_weight_reference.json 표준 단가(만두 13g, 새우튀김 20g)를 곱함.
    "만두장칼국수": [
        ("만두", 52, "[사진중량추정] 만두 4개(사진 확인) × 13g(unit_weight_reference 표준)"),
        ("장칼국수", 790, "105 즉석 검정냄비 실측 기준 표준 790g"),
    ],
    # 사용자 지정: 들깨칼국수(recipe_db에 있음) + 옹심이(개수 세서 반영). 105 즉석.
    "들깨옹심이칼국수": [
        ("옹심이", 56, "[사진중량추정] 옹심이 7개(사진 확인) × 8g(unit_weight_reference 표준)"),
        ("들깨칼국수", 790, "105 즉석 검정냄비 실측 기준 표준 790g"),
    ],
    "새우튀김카레라이스": [
        ("새우튀김", 20, "[사진중량추정] 새우튀김 1개(사진 확인) × 20g(unit_weight_reference 표준)"),
        ("카레라이스", 250, "밥類 단일메뉴 표준 250g"),
    ],
    "새우튀김오므라이스": [
        ("새우튀김", 40, "[사진중량추정] 새우튀김 2개(사진 확인) × 20g(unit_weight_reference 표준)"),
        ("오므라이스", 250, "밥類 단일메뉴 표준 250g"),
    ],
    # 105 한식이라 2026-09-21 그릇 실측 반영(덮밥그릇 표준 570g)
    "새우튀김알밥": [
        ("새우튀김", 40, "[사진중량추정] 새우튀김 2개(사진 확인) × 20g(unit_weight_reference 표준)"),
        ("알밥", 570, "105 한식 덮밥그릇 실측 기준 표준 570g"),
    ],
    # 사용자 지정: 묵은지(토핑) + 참치마요덮밥(베이스). 105 한식이라 그릇 실측 반영.
    "묵은지참치마요덮밥": [
        ("묵은지", 40, "묵은지(토핑) - 표준 반찬 40g"),
        ("참치마요덮밥", 570, "105 한식 덮밥그릇 실측 기준 표준 570g"),
    ],
    # 2026-09-27 추가: 표기 축약/오타로 그 자체 매칭이 안 되는 소스류 - 표준명으로
    # 바꾸고 소스 표준 중량(9g, 1회용 파우치)을 직접 지정. "&"/"," 분리 없이 단독으로
    # 나온 경우라 _special_weight()의 SAUCE_KEYWORDS 판정을 못 타서 override로 처리.
    "타르D": [("타르타르소스", 9, "소스 - 표준 9g(1회용 파우치). 표기 통일: 타르D→타르타르소스")],
    "브라운S": [("브라운소스", 9, "소스 - 표준 9g(1회용 파우치). 표기 통일: 브라운S→브라운소스")],
    # 미소시루(일본식 된장국)는 DB에 없어 기존 우동국물 캐시(가공식품DB 농축액 1:10 희석
    # 보정값)로 대체. 국물류라 40g 기본값 대신 국/탕류 표준 200g을 직접 지정.
    "미소시루": [("우동국물", 200, "국물류 대체(미소시루→우동국물, 기존 1:10 희석 캐시 재사용) - 표준 200g")],
    # 쿨피스는 DB에 없어 제품 라벨(1회 제공량 100mL 기준) 영양성분을 master_cache.json에
    # 직접 입력해서 사용. 1인 제공 컵 기준으로 200g(200mL) 가정(실측치 아님 - 확인 필요).
    "쿨피스": [("쿨피스", 200, "음료 1컵 표준 200g(200mL, 실측 아님- 가정치)")],
    # 2026-09-27 추가: 압축 표기 안에 서로 다른 실제 음식 2개가 들어있는 경우(수식어가 아니라
    # 둘 다 진짜 재료/요리) - 사진으로 실제 비율을 확인할 수 없어 사용자 지시대로 50:50 균등분배.
    "2종전": [
        ("버섯전", 20, "전 2종 중 하나(버섯전) - 사진 없어 50:50 균등분배"),
        ("애호박전", 20, "전 2종 중 하나(애호박전) - 사진 없어 50:50 균등분배"),
    ],
    "새송이브로콜리볶음": [
        ("새송이볶음", 20, "사진 없어 50:50 균등분배"),
        ("브로콜리볶음", 20, "사진 없어 50:50 균등분배"),
    ],
    "제육잡채": [
        ("제육볶음", 20, "사진 없어 50:50 균등분배"),
        ("잡채", 20, "사진 없어 50:50 균등분배"),
    ],
    "미트볼떡볶음": [
        ("미트볼", 20, "사진 없어 50:50 균등분배"),
        ("떡볶이", 20, "사진 없어 50:50 균등분배"),
    ],
    # 청양마요미트볼은 위와 달리 "베이스+소스" 구조(미트볼에 청양마요 소스를 곁들인 것)라
    # 50:50이 아니라 미트볼은 표준 반찬량 그대로, 소스만 9g 추가하는 방식으로 처리.
    "청양마요미트볼": [
        ("미트볼", 40, "미트볼 - 표준 반찬 40g(그대로)"),
        ("청양마요", 9, "소스 - 표준 9g(1회용 파우치)"),
    ],
    # 양파간장은 "간장에 양파를 넣은 소스/양념장"으로 판단, 소스류와 동일하게 소량 처리
    "양파간장": [("양파간장", 9, "소스/양념장 - 표준 9g(1회용 파우치)")],
    # 사용자 지정: "꼬치어묵국"은 국/탕류(200g)가 아니라 꼬치어묵 1개로 취급.
    # unit_weight_reference.json 표준(50g, 실측 아님-추정치) 적용.
    "꼬치어묵국": [("꼬치어묵", 50, "꼬치어묵 1개(unit_weight_reference 추정치, 실측 아님) - 표준 50g")],
    # 2026-09-27 수정: GENERAL_SYNONYMS만으로는 부족함을 발견 - build_item()의 cache.get()은
    # expand_side가 내놓은 표시명("유부장국" 등)을 키로 쓰는데, GENERAL_SYNONYMS는 auto_match()
    # 내부에서만 "우동국물"로 바꾸고 라이브 DB 재검색을 하므로(수동 캐시된 "우동국물" 값은 못 봄)
    # 여전히 실패한다. 미소시루처럼 표시명 자체를 "우동국물"로 바꿔서 수동 캐시를 직접 참조하게 함.
    "유부장국": [("우동국물", 200, "국물류 대체(유부장국→우동국물, 기존 1:10 희석 캐시 재사용) - 표준 200g")],
    "팽이우동국": [("우동국물", 200, "국물류 대체(팽이우동국→우동국물, 기존 1:10 희석 캐시 재사용) - 표준 200g")],
    "팽이장국": [("우동국물", 200, "국물류 대체(팽이장국→우동국물, 기존 1:10 희석 캐시 재사용) - 표준 200g")],
    # 2026-09-27 추가: "삼겹살김치찌개→김치찌개+삼겹살"과 동일 구조("재료명+기본찌개/탕" 결합).
    # 기본 찌개/탕은 food_db/gagong_db에 그대로 있고, 재료만 반찬 함량(40g)으로 얹음.
    "목살김치전골": [
        ("김치전골", 300, "찌개/탕류 - 표준 300g"),
        ("목살", 40, "목살(전골 내 반찬 함량) - 표준 반찬 40g"),
    ],
    "미나리돼지곰탕": [
        ("돼지곰탕", 300, "찌개/탕류 - 표준 300g"),
        ("미나리", 40, "미나리(곰탕 내 반찬 함량) - 표준 반찬 40g"),
    ],
    "소고기우거지해장국": [
        ("우거지해장국", 300, "찌개/탕류 - 표준 300g"),
        ("소고기사태", 40, "소고기(사용자 지정: 원재료DB 수입산 사태 끓인것) - 표준 반찬 40g"),
    ],
    # 사용자 지정: "쭈꾸미만두"는 DB/부분매칭 다 없어 김치만두 삶은것 2개로 대체
    "쭈꾸미만두": [("김치만두", 26, "김치만두 2개(사용자 지정) × 13g(unit_weight_reference 만두 표준)")],
    # 사용자 지정: "OO만두강정"은 만두튀김/튀긴만두 DB에 없어 군만두(구운것, food_db에 있음)로
    # 대체, 3개(사진 확인, 실제로는 4개에 가까워 보이나 지정대로 3개 적용) × 13g, 소스는 생략.
    "맛쵸킹만두강정": [("군만두", 39, "군만두(튀긴 버전 DB에 없어 대체) [사진중량추정] 3개(사진 확인) × 13g - 소스 생략")],
    "명란마요만두강정": [("군만두", 39, "군만두(튀긴 버전 DB에 없어 대체) [사진중량추정] 3개(사진 확인) × 13g - 소스 생략")],
    # 사용자 지정: 장조림+계란후라이+버터10g+쌀밥 구성. 사진(2026-09-04, 204, 일품) 확인 후
    # 그릇 내 비율로 중량 추정(실측 아님) - 밥이 그릇 절반 이상, 장조림/계란이 각각 1/4 수준.
    "장조림버터비빔밥": [
        ("쌀밥", 160, "[사진중량추정] 사진 비율 추정(실측 아님) - 밥공기 기준 다소 많은 양"),
        ("장조림", 60, "[사진중량추정] 사진 비율 추정(실측 아님) - 고기 조각 다수"),
        ("계란후라이", 45, "[사진중량추정] 사진 비율 추정(실측 아님) - 스크램블 형태"),
        ("버터", 10, "버터 1조각(사용자 지정)"),
    ],
    # 사용자 지정: 버섯볶음밥(DB에 표고/새송이/버섯 어떤 조합도 없어 일반 볶음밥으로 대체) + 전복10g.
    # "솥밥" 표준 250g에서 전복 10g 뺀 나머지를 볶음밥으로.
    "전복표고솥밥": [
        ("볶음밥", 240, "버섯볶음밥(DB에 없어 볶음밥으로 대체) - 솥밥 표준 250g 중 전복 제외분"),
        ("전복", 10, "사용자 지정"),
    ],
    # 사용자 지정: 황태(황태구이_양념으로 매칭)+당근+무무침+적양배추+상추+김가루+쌀밥.
    # 105 한식(2026-09-11 사진 확인) - 한식 덮밥그릇 실측 표준 570g 기준으로 그릇 내 비율 추정(실측 아님).
    "황태무침비빔밥": [
        ("쌀밥", 300, "[사진중량추정] 105 한식 덮밥그릇 실측 총량(570g) 중 비율 배분(실측 아님)"),
        ("황태구이_양념", 80, "[사진중량추정] 105 한식 덮밥그릇 실측 총량(570g) 중 비율 배분(실측 아님)"),
        ("무무침", 50, "[사진중량추정] 105 한식 덮밥그릇 실측 총량(570g) 중 비율 배분(실측 아님)"),
        ("적양배추", 40, "[사진중량추정] 105 한식 덮밥그릇 실측 총량(570g) 중 비율 배분(실측 아님)"),
        ("당근", 40, "[사진중량추정] 105 한식 덮밥그릇 실측 총량(570g) 중 비율 배분(실측 아님)"),
        ("상추", 30, "[사진중량추정] 105 한식 덮밥그릇 실측 총량(570g) 중 비율 배분(실측 아님)"),
        ("김가루", 30, "[사진중량추정] 105 한식 덮밥그릇 실측 총량(570g) 중 비율 배분(실측 아님)"),
    ],
    # 사용자 지정: "카레밥" 자체는 DB에 없어 카레+밥으로 분해. 덮밥 표준 250g을 카레/밥으로 배분.
    "토마토커리덮밥": [
        ("카레", 100, "덮밥 표준 250g 중 소스 비중 배분"),
        ("쌀밥", 150, "덮밥 표준 250g 중 밥 비중 배분"),
    ],
    # 사용자 지정: 쌀밥+쪽파+표고버섯+묵은지+우삼겹. 사진(2026-09-14, 401) 확인 후
    # 솥밥 표준 250g 기준 그릇 내 비율 추정(실측 아님) - 우삼겹이 가장 두드러지고
    # 쪽파가 바닥에 넉넉히 깔림, 표고버섯 3조각, 묵은지 적당량.
    "묵은지우삼겹솥밥": [
        ("쌀밥", 130, "[사진중량추정] 사진 비율 추정(실측 아님) - 토핑에 가려진 기본 밥량"),
        ("우삼겹", 50, "[사진중량추정] 사진 비율 추정(실측 아님) - 가장 두드러진 토핑"),
        ("묵은지", 30, "[사진중량추정] 사진 비율 추정(실측 아님)"),
        ("표고버섯", 20, "[사진중량추정] 사진 비율 추정(실측 아님) - 3조각"),
        ("쪽파", 20, "[사진중량추정] 사진 비율 추정(실측 아님) - 바닥에 넉넉히 깔림"),
    ],
    # 사용자 지정: 도토리묵 + 야채무침(DB에 없어 오이무침으로 대체). 사진 확인 안 함 - 50:50 균등분배.
    "도토리묵야채무침": [
        ("도토리묵", 20, "야채무침(DB에 없어 오이무침으로 대체) - 사진 없어 50:50 균등분배"),
        ("오이무침", 20, "야채무침(DB에 없어 오이무침으로 대체) - 사진 없어 50:50 균등분배"),
    ],
    # 사용자 지정: 마늘쫑 + 뒤에 볶음. 사진(2026-09-10, 204, 정식) 확인 - 맛살(분홍)이 마늘쫑(초록)보다
    # 살짝 많아 보임. "맛살볶음" DB에 없어 게맛살로 대체.
    "마늘쫑맛살볶음": [
        ("마늘쫑", 18, "[사진중량추정] 사진 비율 추정(실측 아님)"),
        ("게맛살", 22, "[사진중량추정] 맛살볶음(DB에 없어 게맛살로 대체) - 사진 비율 추정(실측 아님)"),
    ],
    # 사용자 지정: 마늘쫑 + 뒤에 볶음. 이 트레이는 사진이 없어 50:50 균등분배.
    "마늘쫑야채볶음": [
        ("마늘쫑", 20, "사진 없어 50:50 균등분배"),
        ("야채볶음", 20, "사진 없어 50:50 균등분배"),
    ],
    # 사용자 지정: 등심돈가스(사진 확인, 두툼하게 썰려 소스에 자작하게 덮인 "나베" 스타일) + 쌀밥.
    # 사진(2026-08-25, 204, 일품) 기준 중량 추정(실측 아님).
    "돈까스나베": [
        ("등심돈가스", 130, "[사진중량추정] 사진 비율 추정(실측 아님) - 밥 위를 두툼하게 덮은 양"),
        ("쌀밥", 200, "[사진중량추정] 사진 비율 추정(실측 아님)"),
    ],
    # 사용자 지정: 불고기 + 낙지전골. 사진(2026-08-27, 401) 확인 후 중량 추정(실측 아님).
    "불고기낙지전골": [
        ("불고기", 70, "[사진중량추정] 사진 비율 추정(실측 아님) - 전골 내 얇게 썬 고기"),
        ("낙지전골", 230, "[사진중량추정] 사진 비율 추정(실측 아님) - 전골 표준 300g 중 나머지"),
    ],
    # 사용자 지정: 삼겹살 + 비지찌개. 사진(2026-09-10, 105, 즉석) 확인 - 기존
    # "삼겹살김치찌개→김치찌개+삼겹살" 선례와 동일하게 105 즉석 표준 790g 적용.
    "삼겹살비지찌개": [
        ("비지찌개", 790, "105 즉석 검정냄비 실측 기준 표준 790g"),
        ("삼겹살", 40, "[사진중량추정] 삼겹살(찌개 내 반찬 함량) - 표준 반찬 40g"),
    ],
    # 사용자 지정: 순두부 + 김치국. 사진(2026-09-08, 204) 확인 후 중량 추정(실측 아님).
    "순두부김치국": [
        ("순두부", 60, "[사진중량추정] 사진 비율 추정(실측 아님)"),
        ("김치국", 140, "[사진중량추정] 국/탕류 표준 200g 중 나머지"),
    ],
    # 2026-09-27: 이름에 "간장"이 들어있어 _special_weight()의 SAUCE_KEYWORDS 판정에 먼저 걸려
    # 9g 소스로 잘못 처리되던 버그 수정 - GENERAL_SYNONYMS 대신 여기서 이름+중량 직접 지정.
    "숯불간장불고기": [("불고기", 150, "일반 메인반찬 - 표준 150g")],
    "간장마늘지": [("마늘쫑장아찌", 40, "일반 반찬 - 표준 40g")],
    # 2026-09-27 추가: 로제/마라 퓨전 신메뉴 3종 - "베이스요리 + 소스(고정 9g)" 방식으로 분해.
    # 소스는 9g 고정(1회용 파우치 표준), 베이스요리 중량만 사진 확인해서 추정(실측 아님).
    "로제부대찌개": [
        ("부대찌개", 790, "105 즉석 검정냄비 실측 기준 표준 790g"),
        ("로제소스", 9, "소스 - 표준 9g(1회용 파우치)"),
    ],
    "로제함박스테이크": [
        ("함박스테이크", 150, "[사진중량추정] 사진 비율 추정(실측 아님) - 패티 1장"),
        ("로제소스", 9, "소스 - 표준 9g(1회용 파우치)"),
    ],
    "마라로제닭살덮밥": [
        ("닭갈비", 100, "[사진중량추정] 사진 비율 추정(실측 아님) - 덮밥 표준 250g 중 고기 비중"),
        ("쌀밥", 150, "[사진중량추정] 사진 비율 추정(실측 아님) - 덮밥 표준 250g 중 밥 비중"),
        ("로제소스", 9, "소스 - 표준 9g(1회용 파우치)"),
        ("마라소스", 9, "소스 - 표준 9g(1회용 파우치)"),
    ],
    # 사용자 지정: 훈제오리(사진 확인, 슬라이스 6조각) + 숙주나물찜(DB에 "찜" 표기 없어 숙주나물로 대체).
    "훈제오리야채찜": [
        ("훈제오리", 90, "[사진중량추정] 사진 비율 추정(실측 아님) - 슬라이스 6조각"),
        ("숙주나물", 70, "[사진중량추정] 숙주나물찜(DB에 없어 숙주나물로 대체) - 사진 비율 추정(실측 아님)"),
    ],
    # 사용자 지정: 떡갈비 + 야채조림(DB에 없어 감자조림으로 대체, 사진상 감자/당근류 조림).
    "떡갈비야채조림": [
        ("떡갈비", 50, "[사진중량추정] 사진 비율 추정(실측 아님)"),
        ("감자조림", 30, "[사진중량추정] 야채조림(DB에 없어 감자조림으로 대체) - 사진 비율 추정(실측 아님)"),
    ],
    # 사용자 지정: 맛살(게맛살로 대체) + 야채볶음, 50:50 균등분배로 변경(기존 "야채볶음" 단순 치환에서 수정)
    "맛살야채볶음": [
        ("게맛살", 20, "맛살(DB에 없어 게맛살로 대체) - 50:50 균등분배"),
        ("야채볶음", 20, "50:50 균등분배"),
    ],
    # 사용자 지정: 쌀밥 + 김가루 18g(고정)
    "김가루밥": [
        ("쌀밥", 150, "일반 반찬(밥) - 표준 150g"),
        ("김가루", 18, "사용자 지정 고정값"),
    ],
    # 사용자 지정: 주먹밥_참치(food_db) + 김가루(사진 확인)
    "참치김가루밥": [
        ("주먹밥_참치", 130, "[사진중량추정] 사진 비율 추정(실측 아님)"),
        ("김가루", 20, "[사진중량추정] 사진 비율 추정(실측 아님) - 밥에 넉넉히 섞임"),
    ],
    # 사용자 지정: 쌀밥+김가루+계란지단+양념닭강정(사진 확인, 4등분 그릇) + 마요네즈 9g(고정)
    "치킨마요덮밥": [
        ("양념닭강정", 90, "[사진중량추정] 사진 비율 추정(실측 아님) - 그릇의 절반 가까이 차지"),
        ("계란지단", 30, "[사진중량추정] 사진 비율 추정(실측 아님)"),
        ("김가루", 25, "[사진중량추정] 사진 비율 추정(실측 아님)"),
        ("쌀밥", 95, "[사진중량추정] 사진 비율 추정(실측 아님)"),
        ("마요네즈", 9, "사용자 지정 고정값"),
    ],
}

# 2026-09-27 추가: DECOMPOSE_OVERRIDES에 손으로 등록한 컴포넌트 이름 전체(= 메뉴 통짜가 아니라
# 재료/반찬 단위로 직접 쪼갠 이름들). run_pipeline.py가 이 이름들을 매칭할 때는
# auto_match(name, prefer_db104=True)를 써서 원재료DB(db104)를 먼저 보게 한다 - food_db/
# gagong_db에 이름이 비슷한 엉뚱한 가공품이 우연히 먼저 걸리는 문제(예: "당근"이 가공식품
# 200.5kcal에 먼저 걸림)를 막기 위함. 완성요리/가공품 이름은 db104에 애초에 없어서
# 이 우선순위를 적용해도 안전하게 기존 cascade로 통과된다.
RAW_COMPONENT_NAMES = {p for parts in DECOMPOSE_OVERRIDES.values() for p, w, note in parts}


def expand_main(name, shop=None, category=None):
    if name in DECOMPOSE_OVERRIDES:
        return DECOMPOSE_OVERRIDES[name]
    if shop == "105":
        return expand_compound(name, lambda n: classify_main_weight_105(category, n))
    if shop == "401":
        return expand_compound(name, lambda n: classify_main_weight_401(category, n))
    return expand_compound(name, classify_main_weight)
# (401 사이드는 아래 expand_side에서 SAUCE_OR_UDON_401을 extra_special_names로 넘겨
# "돈가스&소스"처럼 컴파운드 조각 중 하나로 섞인 소스/우동국류도 조각 단위로 흰색
# 소스그릇(168g)이 적용되게 한다 - 안 그러면 전체를 반찬 몫으로 묶어 N등분해버림)


def expand_side(name, shop=None, category=None):
    if name in DECOMPOSE_OVERRIDES:
        return DECOMPOSE_OVERRIDES[name]
    if shop == "105":
        return expand_compound(name, lambda n: classify_side_weight_105(category, n))
    if shop == "401":
        return expand_compound(name, lambda n: classify_side_weight_401(category, n), extra_special_names=SAUCE_OR_UDON_401)
    return expand_compound(name, classify_side_weight)


# 2026-09-21: "&"(그리고)/"*"(메인+소스,사리 등)/"/"(둘 중 하나) 구조 분해.
# 메뉴판 표기가 압축돼서 한 토큰 안에 실제로는 2개 이상의 항목이 들어있는 경우를
# 코드 레벨 규칙으로 풀어서 각각 독립적으로 매칭·계산한다(사전에 하드코딩하지 않음 -
# 새 날짜가 추가돼도 같은 패턴이면 자동으로 풀림).
SAUCE_KEYWORDS = ("케찹", "머스타드", "타르소스", "타르타르소스", "칠리소스", "초장",
                   "간장", "잼", "마요")
SARI_KEYWORDS = ("사리",)


def resolve_or(name):
    """"잡곡밥/현미밥"처럼 '/'(또는 "콜라or사이다"처럼 "or")로 두 옵션 중 하나만
    실제로 나가는 표기는 어느 게 나갔는지 알 수 없으므로 첫 번째 옵션을 대표값으로 채택한다."""
    if "/" in name:
        first = name.split("/")[0].strip()
        return first if first else name
    if "or" in name:
        first = name.split("or")[0].strip()
        return first if first else name
    return name


def _special_weight(part):
    """소스/사리 단독 표기(& / * 분리든 단일 토큰이든 공통)의 표준 중량 판정.
    2026-09-27: 학식 소스는 전부 1회용 파우치 제공이라 실측 기준 9g으로 통일(기존 10g에서 수정)."""
    if part.endswith("덮밥"):
        return None
    if any(k in part for k in SARI_KEYWORDS):
        return 150, "사리 추가면 - 표준 150g(면류 표준 300g의 절반)"
    if any(k in part for k in SAUCE_KEYWORDS):
        return 9, "소스/토핑 - 표준 9g(1회용 파우치 실측 기준)"
    return None


def _resolve_part(p, classify_fn):
    """조각 하나(part)를 (표시명, 중량, 근거) 리스트로 변환.
    우선순위: DECOMPOSE_OVERRIDES(표기 교정+고정중량, 여러 항목으로 더 쪼개질 수 있음)
    > 소스/사리 특수처리(고정 소량) > 일반 classify_fn(표준중량).
    2026-09-27 추가: "생선가스&타르D"처럼 DECOMPOSE_OVERRIDES 대상 이름이 "&"/","로 묶인
    조각 중 하나로만 등장하면 예전엔 이 함수를 안 타서(최상위 name 전체만 override 검사)
    "타르D"가 표기 교정도 못 받고 그냥 일반 반찬 40g으로 잘못 계산되고 있었음 - 조각 단위로도
    override를 검사하도록 고침."""
    if p in DECOMPOSE_OVERRIDES:
        return list(DECOMPOSE_OVERRIDES[p])
    sp = _special_weight(p)
    if sp is not None:
        return [(p, sp[0], sp[1])]
    w, note = classify_fn(p)
    return [(p, w, note)]


def expand_compound(name, classify_fn, extra_special_names=None):
    """name을 (표시명, 중량g, 중량근거) 리스트로 분해.
    - '&' / ','(둘 다 순수 "그리고"): 분해 전에 ","를 "&"로 정규화해서 한 번에 같이 쪼갠다
      (2026-09-27 수정: "모닝빵,크로와상&버터,잼"처럼 "&" 안에 ","가 섞인 표기가 실제로 있는데,
      예전엔 "&"만 먼저 걸려서 "모닝빵,크로와상"/"버터,잼"이라는 통짜 조각 2개로만 쪼개지고
      그 안의 ","가 다시 안 풀려서 계속 미매칭으로 남는 버그가 있었음).
    - '*': 메인+소스/사리가 흔하지만 항상 그런 건 아니라 &와 동일 판정 로직을 씀
    - 조각 중 하나라도 DECOMPOSE_OVERRIDES 대상이거나 소스/사리 키워드면: 그 조각만 표기
      교정/고정 소량(소스9g/사리150g) 처리, 나머지 조각은 각자 자기 이름 기준으로 classify_fn을
      다시 불러 원래 표준중량 그대로 유지 (예: "치킨너겟*머스타드" -> 치킨너겟 40g(그대로) + 머스타드 9g)
    - 그런 조각이 하나도 없으면(둘 다 진짜 반찬/가니시, 예: "오이피클&포기김치", "락교*초생강"):
      원래 이름 전체 기준 표준중량을 조각 수만큼 균등분배
      (예: 오이피클&포기김치 40g -> 오이피클 20g + 포기김치 20g)
    - 구분기호가 아예 없는 단일 토큰도 위와 동일한 우선순위(override > 소스/사리 > classify_fn) 적용.
    """
    name = resolve_or(name)
    name = name.replace(",", "&")
    if "&" in name:
        parts = [p.strip() for p in name.split("&") if p.strip()]
    elif "*" in name:
        parts = [p.strip() for p in name.split("*") if p.strip()]
    else:
        return _resolve_part(name, classify_fn)

    if len(parts) < 2:
        return _resolve_part(name, classify_fn)

    def is_special(p):
        if extra_special_names and p in extra_special_names:
            return True
        return p in DECOMPOSE_OVERRIDES or _special_weight(p) is not None

    has_special = any(is_special(p) for p in parts)

    out = []
    if has_special:
        for p in parts:
            if is_special(p):
                out.extend(_resolve_part(p, classify_fn))
            else:
                w, note = classify_fn(p)
                out.append((p, w, note + " (원본 표기 분리)"))
    else:
        base_w, base_note = classify_fn(name)
        share = base_w / len(parts)
        for p in parts:
            out.append((p, share, base_note + f" (& / , 분리, {len(parts)}등분)"))
    return out


def load_cache():
    with open(os.path.join(PIPELINE_DIR, "master_cache.json"), encoding="utf-8") as f:
        return json.load(f)

# 2026-09-21: Fulgoni, Keast & Drewnowski (2009) "Development and Validation of the
# Nutrient-Rich Foods Index" 원문 Table 1의 공식 구조(6+3 영양소, 합산 방식)는 그대로 쓰고,
# DV 기준값은 논문 발표 당시(2009)의 옛 FDA 라벨값 대신 **2016년 개정 FDA %DV**로 교체.
#   NRF6.3 = (단백질/50g + 식이섬유/28g + 비타민A/900µgRAE + 비타민C/90mg + 칼슘/1300mg + 철/18mg
#             − 포화지방/20g − 당류/125g − 나트륨/2300mg) x 100
# - 평균(÷6, ÷3) 아니라 합(sum) - 논문이 "sums가 가장 단순하고 모든 영양소를 동등하게
#   가중하는 방식이라 이걸 채택했다"고 명시(mean은 사실상 가중치를 주는 것과 같다고 함).
# - 100kcal 기준 정규화 - 논문은 RACC(미국 1회제공량) 기준도 같이 검증했지만, RACC가
#   없는 미국 밖 지역은 100kcal 기준을 쓰라고 명시적으로 권장 - 한국 데이터라 100kcal 기준 채택.
# - 당류는 "첨가당 50g" 대신 "총당류 125g" 유지 - FDA 2016 라벨의 "첨가당" DV는 저희 DB에
#   없는 값이라(총당류만 있음) 적용 불가. 논문이 첨가당 데이터 없을 때 제시한 총당류 대체값
#   125g을 그대로 씀(이 값 자체는 2009/2016 어느 쪽도 아닌 논문의 대체 제안치).
# - 비타민A/식이섬유/비타민C/칼슘/나트륨: 2016년 FDA 영양성분표 개정판 %DV 기준(단백질·철·
#   포화지방은 2016 개정에서도 안 바뀌어 논문값과 동일).
DV = {
    "단백질_g": 50, "식이섬유_g": 28, "칼슘_mg": 1300, "철_mg": 18,
    "비타민A_ugRAE": 900, "비타민C_mg": 90,
    "포화지방_g": 20, "당류_g": 125, "나트륨_mg": 2300,
}
BENEFICIAL = ["단백질_g", "식이섬유_g", "칼슘_mg", "철_mg", "비타민A_ugRAE", "비타민C_mg"]
DISQUALIFYING = ["포화지방_g", "당류_g", "나트륨_mg"]


def build_item(name, weight_g, weight_note, cache):
    m = cache.get(name)
    if m is None:
        return {"display": name, "matched": False, "weight_g": weight_g, "weight_note": weight_note,
                "contrib": {f: 0 for f in NUT_FIELDS}, "missing": NUT_FIELDS[:], "source": None}
    per100 = m["per100"]
    missing = [f for f in NUT_FIELDS if per100.get(f) is None]
    contrib = {f: (per100.get(f) or 0) * weight_g / 100.0 for f in NUT_FIELDS}
    return {"display": name, "matched": True, "weight_g": weight_g, "weight_note": weight_note,
            "contrib": contrib, "missing": missing, "source": m.get("source"), "db_name": m.get("name")}


def all_match_names(lunch):
    """이 트레이 계산에 실제로 매칭을 시도할 원자 단위 이름 전체(& / * / 분해 반영).
    run_pipeline.py의 매칭 단계가 압축 표기가 아니라 분해된 실제 이름 기준으로
    캐시를 채우도록 build_month와 동일한 분해 로직을 그대로 재사용한다."""
    main = lunch["main"]
    shop, category = lunch["shop"], lunch["category"]
    sides = [s for s in lunch["sides"] if not is_self_or_junk(s)]
    names = [p for p, _, _ in expand_main(main, shop, category)]
    for s in sides:
        names.extend(p for p, _, _ in expand_side(s, shop, category))
    return names


def compute_tray(lunch, cache):
    main = lunch["main"]
    shop, category = lunch["shop"], lunch["category"]
    sides = [s for s in lunch["sides"] if not is_self_or_junk(s)]

    items = []
    for p, w, note in expand_main(main, shop, category):
        items.append(build_item(p, w, note, cache))
    for s in sides:
        for p, w, note in expand_side(s, shop, category):
            items.append(build_item(p, w, note, cache))

    total = {f: 0.0 for f in NUT_FIELDS}
    tw = 0.0
    n_unmatched = 0
    n_gagong = 0
    missing_list = []
    unmatched_list = []
    gagong_list = []
    nutri_source = {"food_db": [], "recipe_decompose": [], "gagong_db": []}
    for it in items:
        for f in NUT_FIELDS:
            total[f] += it["contrib"][f]
        tw += it["weight_g"]
        if not it["matched"]:
            n_unmatched += 1
            unmatched_list.append(it["display"])
        else:
            if it["missing"]:
                missing_list.append(f'{it["display"]}: ' + ",".join(it["missing"]))
            if it["source"] == "gagong_db":
                n_gagong += 1
                gagong_list.append(it["display"])
            if it["source"] in nutri_source:
                nutri_source[it["source"]].append(it["display"])

    recomputed = total["carb"] * 4 + total["protein"] * 4 + total["fat"] * 9
    diff_ratio = abs(recomputed - total["kcal"]) / total["kcal"] if total["kcal"] > 0 else 0
    reverse_ok = diff_ratio <= 0.10

    # Fulgoni et al.(2009) 원문 그대로: 100kcal 기준으로 정규화한 뒤 %DV를 "합"(sum, 평균 아님)한다.
    kcal_scale = 100.0 / total["kcal"] if total["kcal"] > 0 else 0
    ben = sum(min((total[db_f_map] * kcal_scale) / DV[nrf_f], 1) * 100 for nrf_f, db_f_map in
              zip(BENEFICIAL, ["protein", "fiber", "ca", "fe", "vitA", "vitC"]))
    dis = sum(min((total[db_f_map] * kcal_scale) / DV[nrf_f], 1) * 100 for nrf_f, db_f_map in
              zip(DISQUALIFYING, ["satFat", "sugar", "na"]))
    nrf = round(ben - dis, 1)

    n_missing_fields = sum(len(it["missing"]) for it in items if it["matched"])
    if n_unmatched == 0 and n_missing_fields == 0 and reverse_ok:
        confidence = "높음"
    elif reverse_ok and n_unmatched == 0 and n_missing_fields <= 4:
        confidence = "보통"
    else:
        confidence = "낮음"

    # 2026-09-26: 식품교환단위(6개 식품군) 산출 - 단계적 검증 방침에 따라 우선 105 학생식당만
    # 적용. exchange_unit.py가 MenuGen -> recipe_db -> db104 직접매칭 순으로 재료를 찾아
    # 교환단위를 계산하며, 실패한 항목은 트레이를 통째로 버리지 않고 개별적으로 표시한다.
    exchange_units = None
    if shop == "105":
        exch_totals = {g: 0.0 for g in EXCHANGE_GROUPS}
        exch_unmatched = []
        external_recipes = []
        recipe_notes = []
        exch_source = {"menugen": [], "recipe_db": [], "db104_direct": []}
        for it in items:
            # 우동국 및 지정 조미료는 교환단위 계산에서 제외한다. 영양소 계산은 유지한다.
            if it["display"] in ("우동국", "우동국물", "미소국", "미소장국", "케찹", "케첩", "간장", "초간장", "초장"):
                continue
            exchange_weight = (9.0 if "마요덮밥" in main else 12.0) if it["display"] == "마요네즈" else it["weight_g"]
            r = compute_exchange_units(it["display"], exchange_weight)
            if r.get("recipe_note"):
                recipe_notes.append(r["recipe_note"])
            if it["display"] in ("황태구이_양념", "황태구이 양념") and r["matched"]:
                recipe_notes.append('황태구이_양념: MenuGen 북어구이(고추장)으로 대체 계산. 기존 사진 추정 제공량 80g 적용. 황태무침과 북어구이의 조리 방식·배합 차이는 미보정한 대체 추정값.')
            if it["display"] in ("차돌된장찌개", "차돌 된장찌개") and r["matched"]:
                recipe_notes.append('차돌된장찌개: MenuGen 차돌박이된장찌개로 대체 계산. 기존 제공량에 DB 재료 배합을 비례 환산한 추정값, 실제 배합과 조리수율 차이 미보정.')
            if it["display"] in ("묵은지", "묵은 김치") and r["matched"]:
                recipe_notes.append("묵은지를 배추김치 성분으로 대체하여 기존 추정 제공량 기준 교환단위 계산. 숙성 차이 미보정.")
            if it["display"] == "부타동" and r["matched"]:
                recipe_notes.append('부타동: 사진 비율에 따라 총 표준 추정량570g을 돼지고기 간장볶음220g + 쌀밥350g으로 배분(실측 아님). 볶음220g은 고기·채소·소스 합계이며 고기만의 중량 아님. MenuGen 삼겹살 기반 간장볶음 전체 배합 적용으로 사진에서 미확인된 양파·당근 등도 포함. 조리 수율 미보정. 영양소 탭은 기존 부타동 가공식품 DB 계산 유지.')
            if it["display"] in ("비프하이라이스", "비프 하이라이스") and r["matched"]:
                recipe_notes.append('비프하이라이스: MenuGen 소고기하이라이스로 대체 계산. 동일 덮밥그릇 사용자 확인에 따라 표준 추정 제공량 570g 적용. DB 재료 배합을 비례 환산한 추정값(생쌀 조리수율 미보정).')
            if it["display"] in ("쌈채소", "쌈야채") and r["matched"]:
                recipe_notes.append("쌈채소를 녹색 치마상추 생것으로 대체하여 기존 추정 제공량 기준 교환단위 계산.")
            if it["display"] == "아쿠아돈까스" and r["matched"]:
                recipe_notes.append('아쿠아돈까스 → 샐러드돈가스 대체 레시피로 교환단위 계산. 채소·소스 배합은 실제 식판과 다를 수 있음. 튀김기름 400g은 튀김용 기름 총량으로 보아 제공량·재료합계에서 제외. 흡수유 중량 미확인으로 추가 지방 미반영. 어린잎채소는 다채 어린잎 성분으로 근사. 조미료 정종·소금·후춧가루는 교환단위 미반영.')
            if it["display"] in ("알밥", "알 밥") and r["matched"]:
                recipe_notes.append('알밥: MenuGen 날치알밥 기준 대체 계산. DB 전체 재료 배합을 제공량에 비례 환산. 생쌀 조리수율 미보정, 실제 배합과 다를 수 있음.')
            if it["display"] in ("옹심이", "찹쌀옹심이") and r["matched"]:
                recipe_notes.append("찹쌀옹심이 대체 가정: 가공식품 DB 탄수화물 52g/100g으로 곡류군 환산. 실제 원재료 미확인, 제공량은 사진 기반 추정.")
            if it["display"] in ("제육볶음", "제육 볶음") and r["matched"]:
                recipe_notes.append('제육볶음: MenuGen 돼지고기볶음(고추장, 야채) 기준 대체 계산. 사진에서 양파·대파로 보이는 채소 확인. DB 전체 재료 배합을 제공량에 비례 환산한 추정값.')
            if it["display"] == "주꾸미덮밥" and r["matched"]:
                recipe_notes.append('주꾸미덮밥 → MenuGen 쭈꾸미볶음덮밥으로 대체 매칭. DB 레시피의 새우 등 전체 재료 유지. 제공량에 비례한 추정이며 생쌀 조리수율 미보정.')
            if it["display"] == "스팸마요덮밥" and r["matched"]:
                recipe_notes.append('스팸마요덮밥: MenuGen 치킨마요덮밥의 닭고기 25g을 통조림 돼지고기 햄(스팸 대체 성분) 25g으로 교체하고 나머지 재료 유지. 학생식당 덮밥 표준 추정량 570g으로 교환단위 환산(소스 9g 오분류 제외). 실제 배합·제공량 실측값 아님. 생쌀 조리수율 미보정. 마요네즈는 9g 고정, 영양소 탭의 덮밥 제공량 오분류도 수정.')
            if it["display"] in ("크림스프", "크림수프", "스프(크림)"):
                recipe_notes.append('크림스프 → 스프(크림): MenuGen DB 이름 연결 완료. 끓인 크림스프 완제품은 조리가공식품류로 분류되어 재료별 교환단위 계산 보류. 교환단위 0으로 확정한 것이 아니며 미매칭 목록에 유지.')
            if it["display"] == "크랩알밥" and r["matched"]:
                recipe_notes.append('크랩알밥: MenuGen 날치알밥 + 게맛살로 대체 매칭. 총 제공량 570g 중 게맛살은 DB 기준 30g으로 가정하고 날치알밥에 540g 배분. 실제 중량 실측값 아님. 날치알밥 DB 원재료 비율로 환산하며 생쌀 조리수율은 미보정. 영양소 탭은 기존 계산 유지.')
            if it["display"] == "차돌짬뽕밥" and r["matched"]:
                recipe_notes.append('차돌짬뽕밥: MenuGen 차돌박이짬뽕국 790g + 쌀밥 275g으로 분리하여 교환단위 계산. 국·밥 중량은 기존 학생식당 그릇 기반 표준 추정량이며 실제 음식 무게 실측값 아님. 영양소 탭은 기존 계산 유지.')
            if it["display"] in ("참치야채비빔밥", "참치 야채비빔밥") and r["matched"]:
                recipe_notes.append('참치야채비빔밥: MenuGen 참치생야채비빔밥 기준 대체 계산. 대체 레시피 사용으로 실제 채소·참치·양념 배합과 차이가 있을 수 있음.')
            if it["display"] in ("계란지단", "달걀지단") and r["matched"]:
                recipe_notes.append('계란지단: 원재료DB 달걀, 부침(달걀프라이) 기준 대체 추정. 난류 단백질로 어육류군 계산, 조리용 기름은 별도 지방군으로 분해하지 않음.')
            if it["display"] in ("견과류멸치볶음", "견과류 멸치볶음") and r["matched"]:
                recipe_notes.append('견과류멸치볶음: MenuGen 멸치볶음(견과류) 기준 대체 계산. 메뉴명을 정리하여 견과류 포함 레시피로 계산.')
            if it["display"] in ("고기산적조림", "고기산적 조림") and r["matched"]:
                recipe_notes.append('고기산적조림: MenuGen 퓨전떡갈비 기준 대체 계산. 대체 레시피 추정. 실제 패티 배합·곁들임 피망·조림 소스는 확인되지 않아 차이가 있을 수 있음.')
            if it["display"] in ("고추잎무침", "고춧잎무침") and r["matched"]:
                recipe_notes.append('고추잎무침: MenuGen 고춧잎나물 기준 대체 계산. 표기 차이를 정리하여 고춧잎나물 레시피로 계산.')
            if it["display"] in ("단무지무침", "단무지 무침") and r["matched"]:
                recipe_notes.append('단무지무침: MenuGen 단무지 기준 대체 계산. 추가 양념은 미반영.')
            if it["display"] in ("대패삼겹살", "대패 삼겹살") and r["matched"]:
                recipe_notes.append('대패삼겹살: MenuGen 삼겹살구이 기준 대체 계산. 대패 형태를 기본 삼겹살구이로 대체한 추정치.')
            if it["display"] == "딤섬" and r["matched"]:
                recipe_notes.append('딤섬: 삼색딤섬 대체 레시피. 다진 소고기는 한우 살코기, 통깨는 흰 참깨로 근사. 색소 재료인 백년초가루·뽕잎가루·치자가루는 DB 매칭 불가로 계산에서 제외. 실제 피·속재료 배합과 차이가 있을 수 있음.')
            if it["display"] in ("떡고기산적조림", "떡고기산적 조림") and r["matched"]:
                recipe_notes.append('떡고기산적조림: MenuGen 퓨전떡갈비 기준 대체 계산. 대체 레시피 추정. 실제 패티 배합·곁들임 피망·조림 소스는 확인되지 않아 차이가 있을 수 있음.')
            if it["display"] in ("마늘쫑장아찌", "마늘종장아찌") and r["matched"]:
                recipe_notes.append("마늘쫑장아찌: MenuGen 마늘종 장아찌로 표기 통일하여 계산.")
            if it["display"] == "마요네즈":
                recipe_notes.append("마요덮밥의 마요네즈는 사용자 지정 9g으로 계산." if "마요덮밥" in main else "마요네즈 교환단위 제공량 12g: 9/1 사진의 파우치 표시 확인, 8/26 사용자 지정 동일량. 영양소 탭 기존 계산량은 유지.")
            if it["display"] == "피쉬볼볶음" and r["matched"]:
                recipe_notes.append('피쉬볼볶음: MenuGen 어묵볶음(양파)의 양파 30g을 제외하고 나머지 69g 기준으로 제공량에 비례 환산한 대체 레시피 추정. 사진의 피망·파프리카로 보이는 채소는 미반영.')
            if it["display"] in ("쫄깃단무지무침", "쫄깃단무지 무침") and r["matched"]:
                recipe_notes.append('쫄깃단무지무침: MenuGen 단무지 기준 대체 계산. 추가 양념은 미반영.')
            if it["display"] in ("어니언링", "양파링"):
                recipe_notes.append('어니언링 → 양파링: 이름 연결 완료. 튀김옷·흡수유 배합 정보 확인 전 교환단위 계산 보류.')
            if it["display"] == "청포묵무침" and r["matched"]:
                recipe_notes.append('청포묵무침: MenuGen 탕평채(D132066)의 소고기 30g을 제외하고 남은 재료 총중량 207.5g 기준으로 제공량에 비례 환산. 나머지 재료는 유지한 대체 레시피 추정.')
            if r["matched"]:
                for g in EXCHANGE_GROUPS:
                    exch_totals[g] += r["units"][g]
                if r.get("external_recipe"):
                    external_recipes.append(r["external_recipe"])
                if r["source"] in exch_source:
                    if it["display"] == "부타동":
                        exch_source[r["source"]].extend(["돼지고기 간장볶음", "쌀밥"])
                    elif it["display"] == "크랩알밥":
                        exch_source[r["source"]].extend(["날치알밥", "게맛살"])
                    elif it["display"] == "차돌짬뽕밥":
                        exch_source[r["source"]].extend(["차돌박이짬뽕국", "쌀밥"])
                    else:
                        exch_source[r["source"]].append(it["display"])
            else:
                exch_unmatched.append(it["display"])
        exchange_units = {g: round(v, 2) for g, v in exch_totals.items()}
        exchange_units["미매칭_항목"] = exch_unmatched
        exchange_units["매칭DB"] = exch_source
        exchange_units["externalRecipes"] = external_recipes
        exchange_units["recipeNotes"] = recipe_notes

    return {
        "date": lunch["date"], "shop": lunch["shop"], "shopName": lunch["shopName"],
        "category": lunch["category"], "main": main, "price": lunch["price"], "img": lunch["img"],
        "cat_idx": lunch.get("cat_idx", 0),
        "구성요소_목록": [it["display"] for it in items],
        "1인분_제공량_g": round(tw, 1),
        "kcal": round(total["kcal"], 1), "단백질_g": round(total["protein"], 1),
        "지방_g": round(total["fat"], 1), "탄수화물_g": round(total["carb"], 1),
        "당류_g": round(total["sugar"], 1), "식이섬유_g": round(total["fiber"], 1),
        "칼슘_mg": round(total["ca"], 1), "철_mg": round(total["fe"], 2),
        "비타민A_ugRAE": round(total["vitA"], 1), "비타민C_mg": round(total["vitC"], 1),
        "포화지방_g": round(total["satFat"], 2), "나트륨_mg": round(total["na"], 1),
        "NRF6.3": nrf, "역산검증_오차율": round(diff_ratio * 100, 1), "역산검증_일치여부": reverse_ok,
        "신뢰도": confidence,
        "미매칭_항목": unmatched_list, "가공식품DB_출처_항목": gagong_list, "결측_필드": missing_list,
        "영양_매칭DB": nutri_source,
        "식품교환단위": exchange_units,
        "item_detail": items,
    }


if __name__ == "__main__":
    with open(os.path.join(PIPELINE_DIR, "month_lunch_parsed.json"), encoding="utf-8") as f:
        lunches = json.load(f)
    cache = load_cache()

    results = [compute_tray(l, cache) for l in lunches]

    with open(os.path.join(PROJECT_DIR, "month_lunch_trays.json"), "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=1)

    n_unmatched_total = sum(1 for r in results if r["미매칭_항목"])
    n_low_conf = sum(1 for r in results if r["신뢰도"] == "낮음")
    n_err_over10 = sum(1 for r in results if not r["역산검증_일치여부"])
    print(f"total trays: {len(results)}")
    print(f"trays with at least 1 unmatched item: {n_unmatched_total}")
    print(f"낮음 신뢰도: {n_low_conf}")
    print(f"reverse-check FAIL(>10%): {n_err_over10}")
