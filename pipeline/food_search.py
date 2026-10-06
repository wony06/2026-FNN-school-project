import os
import json, re, sys

FOOD_DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'food_db.json')

PRIORITY = [
    "산업체급식(재료량 기반 산출 함량)",
    "외식(분석함량)",
    "외식(프랜차이즈 등 업체 제공 영양정보)",
    "외식(재료량 기반 산출함량)",
    "가정식(분석 함량)",
    "중고등학교급식(재료량 기반 산출함량)",
    "초등학교급식(재료량 기반 산출 함량)",
]
PRI_RANK = {o: i for i, o in enumerate(PRIORITY)}

def norm(s):
    s = re.sub(r"\[.*?\]", "", s)
    s = re.sub(r"<.*?>", "", s)
    s = re.sub(r"\(.*?\)", "", s)
    s = s.replace(" ", "").replace("*", "").strip()
    return s

def load_db():
    with open(FOOD_DB_PATH, encoding="utf-8") as f:
        return json.load(f)

def search(db, query, limit=15):
    q = norm(query)
    exact = [d for d in db if norm(d["name"]) == q]
    contains = [d for d in db if q in norm(d["name"]) and norm(d["name"]) != q]
    exact.sort(key=lambda d: PRI_RANK.get(d["origin"], 99))
    contains.sort(key=lambda d: PRI_RANK.get(d["origin"], 99))
    return exact[:limit], contains[:limit]

if __name__ == "__main__":
    db = load_db()
    query = sys.argv[1]
    exact, contains = search(db, query)
    print(f"=== EXACT ({len(exact)}) ===")
    for d in exact:
        print(f'{d["name"]} | {d["origin"]} | {d["basis"]} | kcal={d["n"]["kcal"]}')
    print(f"=== CONTAINS ({len(contains)}) ===")
    for d in contains[:10]:
        print(f'{d["name"]} | {d["origin"]} | {d["basis"]} | kcal={d["n"]["kcal"]}')
