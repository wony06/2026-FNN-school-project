# -*- coding: utf-8 -*-
"""처음 사진 일괄 다운로드 당시 <채식의날> 태그로 트레이 자체가 제외됐던 날짜(8/28, 9/11
105)는 photo_mapping.json에 아예 없었다. 태그 제외 로직을 없앤 뒤 다시 필요해진 사진만
원본 URL(hanyang_menu_month.json의 img 필드)에서 받아와 기존 관례(800px 폭, JPEG q78,
EXIF 회전 보정)대로 menu_photos_web/에 채워 넣고 photo_mapping.json을 갱신한다."""
import json, os, urllib.request
from PIL import Image, ImageOps
import io

PIPELINE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(PIPELINE_DIR)

TARGETS = [
    ("2026-08-28", "105", "양식"),
    ("2026-08-28", "105", "한식"),
    ("2026-08-28", "105", "즉석"),
    ("2026-09-11", "105", "양식"),
    ("2026-09-11", "105", "한식"),
    ("2026-09-11", "105", "즉석"),
]


def main():
    with open(os.path.join(PROJECT_DIR, "hanyang_menu_month.json"), encoding="utf-8") as f:
        month = json.load(f)
    with open(os.path.join(PROJECT_DIR, "photo_mapping.json"), encoding="utf-8") as f:
        photo_map = json.load(f)

    days_by_date = {d["date"]: d for d in month["days"]}
    out_dir = os.path.join(PROJECT_DIR, "menu_photos_web")

    for date, shop, category in TARGETS:
        skey = f"s{shop}"
        day = days_by_date[date]
        item = next((it for it in day[skey]["items"] if it["category"] == category), None)
        if item is None or not item.get("img") or item["img"].startswith("menu_photos/"):
            print(f"SKIP {date} {shop} {category}: no downloadable img field")
            continue

        req = urllib.request.Request(item["img"], headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as r:
            raw = r.read()

        img = Image.open(io.BytesIO(raw))
        img = ImageOps.exif_transpose(img)
        img = img.convert("RGB")
        if img.width > 800:
            h = int(img.height * 800 / img.width)
            img = img.resize((800, h), Image.LANCZOS)

        fname = f"{date}_{shop}_{category}.jpg"
        out_path = os.path.join(out_dir, fname)
        img.save(out_path, "JPEG", quality=78)

        photo_map[f"{date}_{shop}_{category}"] = fname
        print(f"OK {date} {shop} {category} -> {fname} ({img.width}x{img.height})")

    with open(os.path.join(PROJECT_DIR, "photo_mapping.json"), "w", encoding="utf-8") as f:
        json.dump(photo_map, f, ensure_ascii=False, indent=1)
    print("photo_mapping.json updated")


if __name__ == "__main__":
    main()
