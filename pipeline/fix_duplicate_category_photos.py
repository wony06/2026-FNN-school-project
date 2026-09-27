# -*- coding: utf-8 -*-
"""2026-09-21: 401이 같은 날 같은 category("중식 - Korean Dining")로 메뉴가 2개 나오는
날(로테이션 메뉴 + "놀부부대찌개" 등 상시메뉴)에는 photo_mapping 키가 date+shop+category뿐이라
두 메뉴가 서로 사진을 덮어써버리는 버그가 있었다(사용자가 "놀부부대찌개 사진이 다 다르다"고
지적해서 발견). parse_month.py에 cat_idx를 추가해 구분했고, 이 스크립트는 영향받은 8개
날짜 16개 항목을 각자의 원본 img URL에서 다시 받아와 올바른 파일/매핑으로 되돌린다.
1회성 보정 스크립트 - 이후에는 run_pipeline.py가 cat_idx 기반 키를 정상적으로 계속 사용함."""
import json, os, urllib.request, io
from PIL import Image, ImageOps

PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PHOTO_DIR = os.path.join(PROJECT_DIR, "menu_photos_web")

AFFECTED_DATES = {"2026-08-24", "2026-08-25", "2026-08-27",
                   "2026-09-07", "2026-09-08", "2026-09-09", "2026-09-10", "2026-09-11"}


def fetch_and_save(url, out_path):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=15) as r:
        raw = r.read()
    img = Image.open(io.BytesIO(raw))
    img = ImageOps.exif_transpose(img)
    img = img.convert("RGB")
    if img.width > 800:
        h = int(img.height * 800 / img.width)
        img = img.resize((800, h), Image.LANCZOS)
    img.save(out_path, "JPEG", quality=78)
    return img.width, img.height


def main():
    with open(os.path.join(PROJECT_DIR, "hanyang_menu_month.json"), encoding="utf-8") as f:
        month = json.load(f)
    with open(os.path.join(PROJECT_DIR, "photo_mapping.json"), encoding="utf-8") as f:
        photo_map = json.load(f)

    days_by_date = {d["date"]: d for d in month["days"]}
    category = "중식 - Korean Dining"

    for date in sorted(AFFECTED_DATES):
        items = [it for it in days_by_date[date]["s401"]["items"] if it["category"] == category]
        for idx, item in enumerate(items):
            key = f"{date}_401_{category}" + (f"#{idx}" if idx else "")
            if not item.get("img"):
                photo_map[key] = None
                print(f"SKIP(사진없음) {date} idx={idx} {item['name'][:20]}")
                continue
            fname = f"{date}_401_중식KoreanDining" + (f"_{idx+1}" if idx else "") + ".jpg"
            out_path = os.path.join(PHOTO_DIR, fname)
            w, h = fetch_and_save(item["img"], out_path)
            photo_map[key] = fname
            print(f"OK {date} idx={idx} {item['name'][:20]} -> {fname} ({w}x{h})")

    with open(os.path.join(PROJECT_DIR, "photo_mapping.json"), "w", encoding="utf-8") as f:
        json.dump(photo_map, f, ensure_ascii=False, indent=1)
    print("photo_mapping.json 갱신 완료")


if __name__ == "__main__":
    main()
