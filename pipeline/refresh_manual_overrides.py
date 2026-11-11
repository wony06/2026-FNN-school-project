# -*- coding: utf-8 -*-
"""manual_exchange_overrides.json의 exchangeUnits를 현재 계산 엔진으로 재계산한다(itemOverrides 보존).

교환단위 로직·중량 규칙을 바꾸면 오버라이드의 옛 고정값이 preserve_manual_data에서 재계산값을 덮어쓰므로,
build_month.py 실행 후 build_site_data.py 전에 이 스크립트를 돌린다. 각 항목의 itemOverrides
(calculationName / exchange_weight_g / exchange_excluded_reason 등)는 item_detail에 주입한 뒤 재계산한다.

실행: python pipeline/refresh_manual_overrides.py
"""
import copy
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from preserve_manual_data import ROOT, GROUPS
from build_month import compute_tray_exchanges


def refresh():
    manual = json.loads((ROOT / 'manual_exchange_overrides.json').read_text(encoding='utf-8'))
    trays = {tuple(t[f] for f in ('date', 'shop', 'category', 'main')): t
             for t in json.loads((ROOT / 'month_lunch_trays.json').read_text(encoding='utf-8'))}
    changed = 0
    for entry in manual['entries']:
        tray = trays.get(tuple(entry['key']))
        if tray is None:
            print('skip (tray 없음):', entry['key'])
            continue
        items = copy.deepcopy(tray['item_detail'])
        by_display = {it['display']: it for it in items}
        for patch in entry.get('itemOverrides', []):
            if patch['display'] in by_display:
                by_display[patch['display']].update({k: v for k, v in patch.items() if k != 'display'})
        raw = compute_tray_exchanges(items, tray.get('calculationMain', tray['main']), tray['shop'], tray['date'])
        db = raw['매칭DB']
        eu = {en: raw[kr] for en, kr in GROUPS.items()}
        eu.update(unmatched=raw['미매칭_항목'], externalRecipes=raw['externalRecipes'], recipeNotes=raw['recipeNotes'],
                  matchedDb={'menugen': db['menugen'], 'recipeDb': db['recipe_db'], 'db104': db['db104_direct']})
        old = entry.get('exchangeUnits') or {}
        if 'customRecipes' in old:
            eu['customRecipes'] = old['customRecipes']
        diff = {g: (old.get(g), eu[g]) for g in GROUPS if old.get(g) != eu[g]}
        if diff:
            changed += 1
            print(entry['key'], diff)
        entry['exchangeUnits'] = eu
    (ROOT / 'manual_exchange_overrides.json').write_text(json.dumps(manual, ensure_ascii=False, indent=1), encoding='utf-8')
    print(f'refreshed {len(manual["entries"])} overrides, {changed} changed')


if __name__ == '__main__':
    refresh()
