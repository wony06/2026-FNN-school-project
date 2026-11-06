"""Build the diary search index from the existing local food databases."""
import csv
import gzip
import json
import math
from collections import Counter
from pathlib import Path
import re
import sys
import unicodedata

ROOT = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[1]
OUTPUT = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "web" / "meal-food-index.json.gz"


def number(value):
    try:
        n = float(value)
        return n if math.isfinite(n) and n >= 0 else None
    except (TypeError, ValueError):
        return None


def read_json(name):
    return json.loads((ROOT / name).read_text(encoding="utf-8-sig"))


def entries():
    for row in read_json("food_db.json"):
        yield ("cooked", row["code"], row["name"], row.get("source") or "식품의약품안전처",
               row.get("origin") or "", row.get("catL") or "", row["basis"],
               [row["n"].get(k) for k in ("kcal", "carb", "protein", "fat")])
    for index, row in enumerate(read_json("db104_raw_ingredients.json"), 1):
        yield ("ingredient", row.get("DB10.4색인", f"supplement-{index}"), row["식품명"], "국가표준식품성분표 10.4",
               row.get("출처") or "", row.get("식품군") or "", "100g",
               [row.get(k) for k in ("에너지", "탄수화물", "단백질", "지방")])
    with (ROOT / "gagong_db_nrf63.csv").open(encoding="utf-8-sig", newline="") as stream:
        for row in csv.DictReader(stream):
            yield ("processed", row["식품코드"], row["식품명"], "식약처 가공식품 DB",
                   row.get("제조사명") or "", row.get("식품소분류명") or "",
                   row["영양성분함량기준량"],
                   [row.get(k) for k in ("에너지(kcal)", "탄수화물(g)", "단백질(g)", "지방(g)")])


def main():
    counts = Counter()
    seen = Counter()
    with OUTPUT.open("wb") as target, gzip.GzipFile(filename="", fileobj=target, mode="wb", compresslevel=6, mtime=0) as stream:
        stream.write(b"[")
        for kind, code, name, source, detail, food_type, basis, nutrients in entries():
            name = name.strip()
            if not name:
                continue
            identity = f"{kind}:{code}"
            seen[identity] += 1
            if seen[identity] > 1:
                identity += f":{seen[identity]}"
            key = re.sub(r"\s+", "", unicodedata.normalize("NFKC", name).lower())
            row = [identity, name, source, detail, food_type, basis, *map(number, nutrients), key]
            if counts.total():
                stream.write(b",")
            stream.write(json.dumps(row, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
            counts[kind] += 1
        stream.write(b"]")
    print(dict(counts), "bytes:", OUTPUT.stat().st_size)


if __name__ == "__main__":
    main()
