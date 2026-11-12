"""Export already calculated recipe per100 values for diary search; never use serving.

Does not calculate a new recipe or overwrite any nutrient/reference source.
"""
import json
import math
import re
import unicodedata
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def build(root=ROOT):
    cache = json.loads((root / 'pipeline/master_cache.json').read_text(encoding='utf-8-sig'))
    recipes = json.loads((root / 'recipe_db_full.json').read_text(encoding='utf-8-sig'))
    types = {row['name']: row.get('cat', '') for row in recipes}
    rows = []
    for key, food in cache.items():
        if not isinstance(food, dict) or food.get('source') != 'recipe_decompose':
            continue
        values = food.get('per100')
        if not isinstance(values, dict):
            continue
        name = food.get('name') or key
        nutrients = [values.get(k) for k in ('kcal', 'carb', 'protein', 'fat')]
        nutrients = [v if isinstance(v, (int, float)) and math.isfinite(v) and v >= 0 else None for v in nutrients]
        unit = str(food.get('unit', 'g')).lower()
        if unit not in ('g', 'ml'):
            continue
        note = food.get('note', '')
        partial = bool(food.get('n_unmatched_ingredients') or food.get('unmatched_ingredients')
                       or any(s in note for s in ('결측', '미확인', '미반영', '과소추정')))
        normalized = re.sub(r'\s+', '', unicodedata.normalize('NFKC', name).lower())
        rows.append(['recipe:' + key, name, '기존 레시피 재료매칭 계산값', '레시피→원재료 DB',
                     types.get(name, ''), '100' + unit, *nutrients, normalized,
                     {'incomplete': ['kcal', 'carb', 'protein', 'fat'] if partial else [],
                      'note': note, 'cacheKey': key, 'source': 'pipeline/master_cache.json'}])
    output = root / 'web/meal-recipe-index.json'
    output.write_text(json.dumps(rows, ensure_ascii=False, separators=(',', ':')) + '\n', encoding='utf-8')
    return {'recipes': len(rows), 'partialRecipes': sum(bool(r[11]['incomplete']) for r in rows), 'output': 'web/meal-recipe-index.json'}


if __name__ == '__main__':
    print(json.dumps(build(), ensure_ascii=False))
