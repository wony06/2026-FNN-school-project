"""승인된 5개 영양성분만 현재 실행 데이터에 반영. 다른 계산 결과는 보존."""
import copy
import hashlib
import json
from pathlib import Path
from approved_nov_nutrition import apply_approved_nutrition
from build_month import summarize_nutrition

ROOT = Path(__file__).resolve().parents[1]
FIELDS = {'kcal':'kcal', 'protein':'단백질_g', 'fat':'지방_g', 'carb':'탄수화물_g',
          'sugar':'당류_g', 'fiber':'식이섬유_g', 'ca':'칼슘_mg', 'fe':'철_mg',
          'vitA':'비타민A_ugRAE', 'vitC':'비타민C_mg', 'satFat':'포화지방_g', 'na':'나트륨_mg'}


def load(path):
    return json.loads((ROOT/path).read_text(encoding='utf-8'))


def save(path, data, compact=False):
    original = (ROOT/path).read_bytes()
    newline = '\r\n' if b'\r\n' in original else '\n'
    (ROOT/path).write_text(json.dumps(data, ensure_ascii=False, **({} if compact else {'indent':1})),
                           encoding='utf-8', newline=newline)


def key(row):
    return tuple(row[f] for f in ('date', 'shop', 'category', 'main'))


def main():
    trays = load('month_lunch_trays.json')
    changes = {}
    for tray in trays:
        before = copy.deepcopy(tray)
        apply_approved_nutrition(tray['item_detail'], tray)
        if tray == before:
            continue
        total, tw, nrf, diff, reverse, confidence, unmatched, gagong, missing, source = summarize_nutrition(tray['item_detail'])
        for field, kr in FIELDS.items():
            tray[kr] = round(total[field], 2 if field in ('fe', 'satFat') else 1)
        tray.update({'NRF6.3':nrf, '역산검증_오차율':round(diff*100,1), '역산검증_일치여부':reverse,
                     '신뢰도':confidence, '미매칭_항목':unmatched, '가공식품DB_출처_항목':gagong,
                     '결측_필드':missing, '영양_매칭DB':source})
        assert tray['식품교환단위'] == before['식품교환단위']
        changes[key(tray)] = tray
    for path in ('site_data.json', 'web/site_data.json'):
        rows = load(path)
        for row in rows:
            tray = changes.get(key(row))
            if tray is None:
                continue
            for field, kr in FIELDS.items():
                row[field] = tray[kr]
            row.update({'nrf':tray['NRF6.3'], 'confidence':tray['신뢰도'],
                        'unmatched':tray['미매칭_항목'], 'gagongSourced':tray['가공식품DB_출처_항목'],
                        'matchedDb':{'foodDb':tray['영양_매칭DB']['food_db'],
                                     'recipeDecompose':tray['영양_매칭DB']['recipe_decompose'],
                                     'gagongDb':tray['영양_매칭DB']['gagong_db']}})
            by_name = {i['display']:i for i in tray['item_detail'] if i.get('nutritionRecipe')}
            for item in row['itemDetails']:
                if item['display'] in by_name:
                    patch = by_name[item['display']]
                    for field in ('matched','contrib','missing','source','db_name','weight_note','nutritionRecipe','nutritionIngredients'):
                        item[field] = copy.deepcopy(patch[field])
        save(path, rows, compact=True)
    save('month_lunch_trays.json', trays)
    snapshot = load('web/menu_exchange_snapshot.json')
    snapshot['sourceSha256'] = hashlib.sha256((ROOT/'web/site_data.json').read_bytes()).hexdigest()
    save('web/menu_exchange_snapshot.json', snapshot)
    print(json.dumps([{'key':k, 'kcal':t['kcal'], 'nrf':t['NRF6.3'], 'unmatched':t['미매칭_항목']}
                      for k,t in changes.items()], ensure_ascii=False))


if __name__ == '__main__':
    main()
