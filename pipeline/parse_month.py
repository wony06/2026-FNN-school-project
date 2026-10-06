# -*- coding: utf-8 -*-
"""hanyang_menu_month.json(스크래핑 원본) -> 중식(점심)만 골라 main/sides로 분해.
새 날짜가 스크래핑돼서 hanyang_menu_month.json에 추가되면 이 스크립트를 다시 돌리면 됨."""
import json, re, os
from datetime import date as _date

PIPELINE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(PIPELINE_DIR)


def is_lunch_cat(skey, category):
    if skey == "s105":
        return category in ("양식", "한식", "즉석")
    if skey == "s401":
        return category.startswith("중식")
    if skey == "s204":
        return category in ("정식", "일품")
    return False


def clean_tag(name):
    """[품절]/<채식의날>/(한정)/[분식데이] 등 대괄호·꺽쇠·소괄호로 감싼 공지성 태그는
    표기 방식에 관계없이 전부 이름에서만 떼어낸다. 메뉴 자체는 제외하지 않고 그대로
    계산 대상에 포함한다 - 이 태그들은 '팔지 않음'이 아니라 코너/날짜 안내문이다."""
    name = re.sub(r"\[.*?\]", "", name)
    name = re.sub(r"<.*?>", "", name)
    name = re.sub(r"\(.*?\)", "", name)
    return name.strip()


def parse_main_and_sides(name, desc):
    """식당 코드로 분기하지 않고 desc의 실제 내용으로 판단한다.
    105는 desc에 진짜 반찬목록이 내려오지만, 401/204는 desc가 항상 "-"(또는 SELF 코너
    안내문)이고 실제 반찬목록은 name 필드에 "주메뉴 반찬1 반찬2 ... 음료"로 공백구분
    되어 다 들어있다. 식당별 하드코딩 대신 이 규칙 하나로 양쪽 다 처리한다."""
    desc = (desc or "").strip()
    is_real_desc = desc not in ("", "-") and "SELF" not in desc.upper()
    if is_real_desc:
        main = clean_tag(name)
        sides = [clean_tag(t) for t in desc.split()]
    else:
        # "[분식데이] 전골떡볶이 ..." 처럼 태그가 그 자체로 공백 구분된 토큰이면
        # clean_tag가 그 토큰을 빈 문자열로 만든다 - 빈 토큰을 먼저 걸러내야
        # main이 빈 문자열이 아니라 진짜 첫 메뉴명("전골떡볶이")이 된다.
        tokens = [clean_tag(t) for t in split_protect_parens(name)]
        tokens = [t for t in tokens if t]
        main = tokens[0] if tokens else clean_tag(name)
        sides = tokens[1:]
    return main, [s for s in sides if s]


def split_protect_parens(s, sep=" "):
    """괄호 안의 공백은 분리 기준으로 안 씀 (예: "비빔밥&계란후라이(밥 따로)"가 안 쪼개지게)"""
    parts, depth, buf = [], 0, []
    for ch in s:
        if ch in "(（":
            depth += 1
            buf.append(ch)
        elif ch in ")）":
            depth = max(0, depth - 1)
            buf.append(ch)
        elif ch == sep and depth == 0:
            parts.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
    if buf:
        parts.append("".join(buf))
    return [p for p in parts if p]


# 2026-09-21: 105 양식(돈까스류)은 desc가 8/24~9/18 전체 20건 전부 "-"라 반찬목록이
# 아예 안 내려온다. 실제로는 밥/샐러드/김치/국이 항상 같이 나가는데(사용자 확인) desc가
# 없어서 지금까지 계산에서 통째로 빠져있었다. 고정 세트로 채워 넣는다.
FIXED_SIDES_OVERRIDE = {
    ("s105", "양식"): ["쌀밥", "샐러드", "김치", "우동국"],  # 2026-09-21: "국"→"우동국"으로 특정(사용자 지정)
}

# 2026-09-21: 메인명 자체가 공백 포함 다어절인데(예: "뼈없는 감자탕") desc가 없어서
# fallback 토큰분리가 첫 단어(수식어)만 main으로 잘라내는 케이스. 새 사례 나오면 추가.
MAIN_PREFIX_MERGE = {
    ("뼈없는", "감자탕"): "감자탕",
}


def parse_month_lunches(hanyang_menu_month_path=None):
    path = hanyang_menu_month_path or os.path.join(PROJECT_DIR, "hanyang_menu_month.json")
    with open(path, encoding="utf-8") as f:
        data = json.load(f)

    lunches = []
    for day in data["days"]:
        date = day["date"]
        # 2026-10-06: 사용자 지시로 주말 메뉴는 아예 안 쓰기로 함 - 이후 전체 파이프라인에
        # 들어가지 않도록 파싱 단계에서부터 평일만 남긴다(build_site_data.py의 주말 필터와
        # 별개로, 여기서 걸러야 미매칭 집계 등 중간 산출물에도 주말이 안 섞인다).
        if _date.fromisoformat(date).weekday() >= 5:
            continue
        for skey, shopnum in (("s105", "105"), ("s401", "401"), ("s204", "204")):
            shop = day.get(skey)
            if not shop:
                continue
            # 2026-09-21: 401은 같은 날 같은 category("중식 - Korean Dining")로 메뉴가
            # 2개 나오는 날이 있다(예: 로테이션 메뉴 + "놀부부대찌개" 상시메뉴). 사진 매핑
            # 키가 date+shop+category만 쓰면 둘이 충돌해서 한쪽 사진을 서로 뺏어가는 버그가
            # 있었음 - category 안에서 몇 번째 항목인지(cat_idx)를 붙여 구분한다.
            cat_counter = {}
            for item in shop["items"]:
                if not is_lunch_cat(skey, item["category"]):
                    continue
                cat_idx = cat_counter.get(item["category"], 0)
                cat_counter[item["category"]] = cat_idx + 1
                main, sides = parse_main_and_sides(item["name"], item["desc"])
                if not sides:
                    sides = FIXED_SIDES_OVERRIDE.get((skey, item["category"]), sides)
                if sides and (main, sides[0]) in MAIN_PREFIX_MERGE:
                    main = MAIN_PREFIX_MERGE[(main, sides[0])]
                    sides = sides[1:]
                lunches.append({
                    "date": date, "shop": shopnum, "shopName": shop["shopName"],
                    "category": item["category"], "main": main, "sides": sides,
                    "price": item["price"], "img": item["img"], "cat_idx": cat_idx,
                })
    return lunches


if __name__ == "__main__":
    lunches = parse_month_lunches()
    out_path = os.path.join(PIPELINE_DIR, "month_lunch_parsed.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(lunches, f, ensure_ascii=False, indent=1)
    print(f"parsed {len(lunches)} lunch trays -> {out_path}")
