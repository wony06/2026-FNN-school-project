import csv, re, sys

GAGONG_PATH = r"C:\Users\ST-USER\Desktop\2026 학술제\gagong_db_nrf63.csv"

def norm(s):
    if not s:
        return ""
    s = re.sub(r"\[.*?\]", "", s)
    s = re.sub(r"<.*?>", "", s)
    s = re.sub(r"\(.*?\)", "", s)
    s = s.replace(" ", "").replace("*", "").strip()
    return s

_CACHE = None
def load_db():
    global _CACHE
    if _CACHE is not None:
        return _CACHE
    rows = []
    with open(GAGONG_PATH, encoding="utf-8-sig", newline="") as f:
        r = csv.DictReader(f)
        for row in r:
            rows.append(row)
    _CACHE = rows
    return rows

def search(db, query, limit=15):
    q = norm(query)
    exact = [d for d in db if norm(d["식품명"]) == q]
    contains = [d for d in db if q and q in norm(d["식품명"]) and norm(d["식품명"]) != q]
    return exact[:limit], contains[:limit]

NUM_FIELDS = ["에너지(kcal)", "단백질(g)", "식이섬유(g)", "칼슘(mg)", "철(mg)",
              "비타민 A(μg RAE)", "비타민 C(mg)", "포화지방산(g)", "당류(g)", "나트륨(mg)"]

def subcategories(exact_matches):
    """정확매칭 결과에 섞여있는 식품소분류명 종류를 보여준다.
    소분류가 2개 이상이면(예: 유자청의 음료형/당절임형) 물성이 다를 수 있으니
    median_group()을 부르기 전에 사용자에게 어느 소분류를 쓸지 먼저 물어볼 것."""
    return sorted(set(d["식품소분류명"] for d in exact_matches))

def median_group(exact_matches):
    """정확매칭된 여러 회사 제품의 NRF6.3 필드를 항목별 중앙값으로 합친다.
    지방(g)/탄수화물(g)은 이 CSV에 없으므로 별도로 원본 xlsx에서 조회해 합쳐야 한다.
    호출 전에 subcategories()로 물성이 섞여있지 않은지 반드시 확인할 것."""
    import statistics
    out = {"_n": len(exact_matches), "_codes": [d["식품코드"] for d in exact_matches]}
    for f in NUM_FIELDS:
        vals = [float(d[f]) for d in exact_matches if d[f] not in (None, "")]
        out[f] = round(statistics.median(vals), 2) if vals else None
    return out

def backfill_fatcarb_for_cache(cache_path, gagong_xlsx_path=None, verbose=True):
    """master_cache.json 안의 gagong_db 출처 항목 중 지방(fat)/탄수화물(carb)이 비어있는 것을
    원본 가공식품DB 엑셀(316,734건)에서 직접 조회해 채워넣는다.

    배경: gagong_db_nrf63.csv는 NRF6.3 계산용으로 지방/탄수화물 컬럼을 뺀 파생본이라,
    auto_match()가 gagong_db로 매칭한 항목은 이 두 필드가 항상 None으로 남는다.
    이걸 방치하면 kcal은 정상인데 지방/탄수화물이 0으로 계산되어, 역산검증(4/4/9 칼로리 재계산)이
    크게 어긋나는 버그가 생긴다(실제로 이 파이프라인 개발 중 3번 반복 발생했던 문제).
    새 메뉴를 auto_match로 매칭한 뒤엔 반드시 이 함수를 한 번 불러서 채워야 한다.

    openpyxl 필요, 316,734행 전체를 한 번 스캔하므로 5~6분 정도 걸림(코드 개수와 무관, 한 번에 처리).
    """
    import json, statistics, openpyxl

    xlsx_path = gagong_xlsx_path or r"C:\Users\ST-USER\Desktop\학술제\20260828_가공식품DB_316734건.xlsx"

    with open(cache_path, encoding="utf-8") as f:
        cache = json.load(f)

    missing_keys = [k for k, v in cache.items()
                     if v and v.get("source") == "gagong_db"
                     and (v["per100"].get("fat") is None or v["per100"].get("carb") is None)]
    if not missing_keys:
        if verbose:
            print("백필 필요한 gagong_db 항목 없음")
        return cache

    db = load_db()
    needed = {}
    for k in missing_keys:
        # 2026-09-21 수정: 캐시 키 이름으로 재검색하면, 그 항목이 동의어 리다이렉트나
        # "포함검색"(완전일치 아님)으로 매칭된 경우 캐시 키 자체는 gagong_db에 완전일치가
        # 없어서 0건이 나온다(냉우동/우동장국/순두부찌개류 등에서 반복 발생했던 버그).
        # try_gagong_db()가 매칭 당시 저장해둔 실제 제품코드(_codes)가 있으면 그걸 우선 쓴다.
        stored_codes = cache[k].get("_codes")
        if stored_codes:
            needed[k] = stored_codes
        else:
            exact, _ = search(db, k, limit=200)
            needed[k] = [d["식품코드"] for d in exact]
    all_codes = set()
    for codes in needed.values():
        all_codes.update(codes)
    if verbose:
        print(f"백필 대상: {len(missing_keys)}개 항목, {len(all_codes)}개 제품코드 조회 중...")

    wb = openpyxl.load_workbook(xlsx_path, read_only=True, data_only=True)
    ws = wb[wb.sheetnames[0]]
    rows_iter = ws.iter_rows(values_only=True)
    header = next(rows_iter)
    header = [h.replace("\ufeff", "") if isinstance(h, str) else h for h in header]
    idx = {h: i for i, h in enumerate(header)}
    fatcarb = {}
    for row in rows_iter:
        code = row[idx["식품코드"]]
        if code in all_codes:
            fatcarb[code] = {"fat": row[idx["지방(g)"]], "carb": row[idx["탄수화물(g)"]]}
            if len(fatcarb) == len(all_codes):
                break

    def to_num(v):
        if v in (None, ""):
            return None
        try:
            return float(v)
        except ValueError:
            return None

    for key, codes in needed.items():
        fats = [v for v in (to_num(fatcarb.get(c, {}).get("fat")) for c in codes) if v is not None]
        carbs = [v for v in (to_num(fatcarb.get(c, {}).get("carb")) for c in codes) if v is not None]
        cache[key]["per100"]["fat"] = round(statistics.median(fats), 2) if fats else None
        cache[key]["per100"]["carb"] = round(statistics.median(carbs), 2) if carbs else None

    with open(cache_path, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=1)
    if verbose:
        print(f"백필 완료: {len(missing_keys)}개 항목 갱신")
    return cache


if __name__ == "__main__":
    db = load_db()
    print("total rows:", len(db))
    query = sys.argv[1]
    exact, contains = search(db, query)
    print(f"=== EXACT ({len(exact)}) ===")
    for d in exact[:10]:
        print(f'{d["식품명"]} | {d["식품중분류명"]} | {d["영양성분함량기준량"]} | kcal={d["에너지(kcal)"]} | 제조사={d["제조사명"]}')
    print(f"=== CONTAINS (first 10) ===")
    for d in contains[:10]:
        print(f'{d["식품명"]} | {d["식품중분류명"]} | {d["영양성분함량기준량"]} | kcal={d["에너지(kcal)"]} | 제조사={d["제조사명"]}')
