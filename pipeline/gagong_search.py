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
              "비타민 A(μg RAE)", "비타민 C(mg)", "포화지방산(g)", "당류(g)", "나트륨(mg)",
              "지방(g)", "탄수화물(g)"]

def subcategories(exact_matches):
    """정확매칭 결과에 섞여있는 식품소분류명 종류를 보여준다.
    소분류가 2개 이상이면(예: 유자청의 음료형/당절임형) 물성이 다를 수 있으니
    median_group()을 부르기 전에 사용자에게 어느 소분류를 쓸지 먼저 물어볼 것."""
    return sorted(set(d["식품소분류명"] for d in exact_matches))

def median_group(exact_matches):
    """정확매칭된 여러 회사 제품의 NRF6.3 필드 + 지방/탄수화물을 항목별 중앙값으로 합친다.
    (2026-10-03: 지방/탄수화물도 원본 엑셀에서 합쳐넣어 CSV 자체에 포함시킴 - 더 이상 별도 백필 불필요)
    호출 전에 subcategories()로 물성이 섞여있지 않은지 반드시 확인할 것."""
    import statistics
    out = {"_n": len(exact_matches), "_codes": [d["식품코드"] for d in exact_matches]}
    for f in NUM_FIELDS:
        vals = [float(d[f]) for d in exact_matches if d[f] not in (None, "")]
        out[f] = round(statistics.median(vals), 2) if vals else None
    return out

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
