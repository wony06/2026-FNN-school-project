# -*- coding: utf-8 -*-
"""month_lunch_trays.json(계산 완료된 전체 필드) -> 웹사이트가 fetch하는 슬림 site_data.json.
run_pipeline.py의 마지막 단계로 자동 실행됨. 단독 실행도 가능."""
import json, os

PIPELINE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(PIPELINE_DIR)


def build_site_data():
    with open(os.path.join(PROJECT_DIR, "month_lunch_trays.json"), encoding="utf-8") as f:
        trays = json.load(f)
    with open(os.path.join(PROJECT_DIR, "photo_mapping.json"), encoding="utf-8") as f:
        photo_map = json.load(f)

    out = []
    for r in trays:
        idx = r.get("cat_idx", 0)
        key = f"{r['date']}_{r['shop']}_{r['category']}"
        if idx:
            key += f"#{idx}"

        eu = r.get("식품교환단위")
        exchange_units = None
        if eu is not None:
            exchange_units = {
                "grain": eu["곡류군"], "meat": eu["어육류군"], "veg": eu["채소군"],
                "fat": eu["지방군"], "dairy": eu["우유군"], "fruit": eu["과일군"],
                "unmatched": eu["미매칭_항목"],
            }

        out.append({
            "date": r["date"], "shop": r["shop"], "shopName": r["shopName"],
            "category": r["category"], "main": r["main"], "price": r["price"],
            "photo": photo_map.get(key),
            "weight": r["1인분_제공량_g"],
            "kcal": r["kcal"], "protein": r["단백질_g"], "fat": r["지방_g"], "carb": r["탄수화물_g"],
            "sugar": r["당류_g"], "fiber": r["식이섬유_g"], "ca": r["칼슘_mg"], "fe": r["철_mg"],
            "vitA": r["비타민A_ugRAE"], "vitC": r["비타민C_mg"], "satFat": r["포화지방_g"], "na": r["나트륨_mg"],
            "nrf": r["NRF6.3"], "confidence": r["신뢰도"],
            "unmatched": r["미매칭_항목"], "gagongSourced": r["가공식품DB_출처_항목"],
            "components": r["구성요소_목록"],
            "exchangeUnits": exchange_units,
        })

    out_path = os.path.join(PROJECT_DIR, "site_data.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False)
    return out_path, len(out)


if __name__ == "__main__":
    path, n = build_site_data()
    print(f"site_data.json 재생성 완료: {n}개 트레이 -> {path}")
