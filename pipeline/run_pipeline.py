# -*- coding: utf-8 -*-
"""학식 영양성분 계산 백엔드 파이프라인 - 전체 실행 스크립트.

새 날짜가 hanyang_menu_month.json에 추가됐을 때, 이 파일 하나만 다시 돌리면
month_lunch_trays.json(웹사이트가 읽는 최종 데이터)까지 자동으로 갱신된다.

순서:
  1. parse_month.py   - 스크래핑 원본에서 중식(점심)만 골라 main/sides로 분해
  2. auto_match.py    - 각 메뉴/반찬명을 food_db -> 1.7단계(레시피DB+db104) -> gagong_db 순으로 매칭
  3. gagong_search.py  - gagong_db로 매칭된 항목의 지방/탄수화물을 원본 엑셀에서 백필(필수! 안 하면 역산검증 깨짐)
  4. build_month.py   - 트레이별로 중량 곱해 합산, NRF6.3 계산, month_lunch_trays.json 저장
  5. build_site_data.py - 웹사이트가 fetch하는 슬림 site_data.json으로 변환(사진 매핑 포함)

실행: python run_pipeline.py
"""
import os, sys, json

PIPELINE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, PIPELINE_DIR)

from parse_month import parse_month_lunches
from auto_match import auto_match
from gagong_search import backfill_fatcarb_for_cache
from build_month import compute_tray, all_match_names, RAW_COMPONENT_NAMES
from build_site_data import build_site_data

CACHE_PATH = os.path.join(PIPELINE_DIR, "master_cache.json")


def main():
    print("[1/5] 메뉴 파싱...")
    lunches = parse_month_lunches()
    with open(os.path.join(PIPELINE_DIR, "month_lunch_parsed.json"), "w", encoding="utf-8") as f:
        json.dump(lunches, f, ensure_ascii=False, indent=1)
    print(f"      {len(lunches)}개 점심 트레이")

    print("[2/5] 메뉴/반찬명 매칭 (food_db -> 1.7단계 -> gagong_db)...")
    with open(CACHE_PATH, encoding="utf-8") as f:
        cache = json.load(f)
    names = set()
    for l in lunches:
        names.update(all_match_names(l))
    new_names = [n for n in names if n not in cache]
    print(f"      전체 {len(names)}개 중 신규 {len(new_names)}개 매칭 중...")
    for n in new_names:
        cache[n] = auto_match(n, prefer_db104=(n in RAW_COMPONENT_NAMES))
    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=1)
    n_unmatched = sum(1 for n in new_names if cache[n] is None)
    print(f"      신규 매칭 실패: {n_unmatched}개 (food_db/gagong_db/db104 어디에도 없음)")

    print("[3/5] gagong_db 항목 지방/탄수화물 백필...")
    backfill_fatcarb_for_cache(CACHE_PATH)

    print("[4/5] 트레이 계산 + NRF6.3...")
    with open(CACHE_PATH, encoding="utf-8") as f:
        cache = json.load(f)
    results = [compute_tray(l, cache) for l in lunches]
    out_path = os.path.join(os.path.dirname(PIPELINE_DIR), "month_lunch_trays.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=1)

    n_bad = sum(1 for r in results if not r["역산검증_일치여부"])
    n_low = sum(1 for r in results if r["신뢰도"] == "낮음")
    n_unmatched_trays = sum(1 for r in results if r["미매칭_항목"])
    print(f"      저장: {out_path}")
    print(f"      총 {len(results)}개 트레이 | 역산검증 실패(>10%): {n_bad} | 신뢰도 낮음: {n_low} | 미매칭 항목 있는 트레이: {n_unmatched_trays}")

    print("[5/5] site_data.json 재생성...")
    site_path, n_site = build_site_data()
    print(f"      {n_site}개 트레이 -> {site_path}")


if __name__ == "__main__":
    main()
