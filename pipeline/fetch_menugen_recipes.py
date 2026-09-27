"""농촌진흥청 국립식량과학원 농식품 식단관리(메뉴젠) 음식/재료/조리 정보 API 전체 다운로드.
이 API는 음식명 검색 파라미터가 없고 Page_No로 전체(3,250건, 1건씩)를 순회하는 구조라,
전체를 한 번 받아 로컬 JSON으로 저장해두고 이후엔 이걸 메뉴명 매칭에 사용한다.
100건마다 진행상황을 저장해서, 중간에 끊겨도 다시 실행하면 이어받는다.
"""
import json
import os
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config import MENUGEN_SERVICE_KEY as SERVICE_KEY
BASE_URL = "https://apis.data.go.kr/1390803/AgriFood/FdFoodCkry1/getKoreanFoodFdFoodCkryList1"
OUT_PATH = r"C:\Users\ST-USER\Desktop\2026 학술제\menugen_recipes.json"
PROGRESS_EVERY = 100


def fetch_page(page_no, retries=3):
    params = {"serviceKey": SERVICE_KEY, "service_Type": "xml", "Page_No": str(page_no)}
    url = BASE_URL + "?" + urllib.parse.urlencode(params)
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(url, timeout=10) as resp:
                data = resp.read()
            return ET.fromstring(data)
        except Exception:
            if attempt == retries - 1:
                raise
            time.sleep(1.5)


def text(el, tag, default=None):
    child = el.find(tag)
    if child is None or child.text is None or child.text == "null":
        return default
    return child.text


def parse_item(item_el):
    ingredients = []
    for food_el in item_el.findall("./food_List/food"):
        ingredients.append({
            "food_code": text(food_el, "food_Code"),
            "food_name": text(food_el, "food_Nm"),
            "food_eng_name": text(food_el, "food_Eng_Nm"),
            "food_group": text(food_el, "nation_Std_Food_Grupp_Code_Nm"),
            "origin": text(food_el, "origin_Code_Nm"),
            "weight_g": text(food_el, "food_Wgh"),
            "allergy": text(food_el, "allrgy_Info"),
        })

    cooking_steps = [c.text for c in item_el.findall("./ckry_List/*") if c.text]

    return {
        "fd_code": text(item_el, "fd_Code"),
        "upper_group": text(item_el, "upper_Fd_Grupp_Nm"),
        "group": text(item_el, "fd_Grupp_Nm"),
        "name": text(item_el, "fd_Nm"),
        "weight_g": text(item_el, "fd_Wgh"),
        "ingredient_count": text(item_el, "food_Cnt"),
        "ingredients": ingredients,
        "cooking_steps": cooking_steps,
    }


def load_progress():
    try:
        with open(OUT_PATH, encoding="utf-8") as f:
            results = json.load(f)
        print(f"기존 진행상황 발견: {len(results)}건. 이어서 받습니다.")
        return results
    except FileNotFoundError:
        return []


def main():
    root = fetch_page(1)
    total_count = int(root.findtext("./body/total_Count", "0"))
    print(f"총 {total_count}건")

    results = load_progress()
    start_page = len(results) + 1

    for page_no in range(start_page, total_count + 1):
        try:
            root = fetch_page(page_no)
        except Exception as e:
            print(f"[{page_no}] 요청 실패: {e}")
            break

        result_code = root.findtext("./header/result_Code")
        if result_code != "200":
            print(f"[{page_no}] 응답 오류: {result_code} {root.findtext('./header/result_Msg')}")
            break

        item_el = root.find("./body/items/item")
        if item_el is None:
            print(f"[{page_no}] item 없음, 건너뜀")
            continue

        results.append(parse_item(item_el))

        if page_no % PROGRESS_EVERY == 0:
            print(f"진행: {page_no}/{total_count}")
            with open(OUT_PATH, "w", encoding="utf-8") as f:
                json.dump(results, f, ensure_ascii=False, indent=2)

        time.sleep(0.05)

    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"완료: {len(results)}건 -> {OUT_PATH}")


if __name__ == "__main__":
    main()
