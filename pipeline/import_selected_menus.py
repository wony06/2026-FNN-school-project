# -*- coding: utf-8 -*-
"""Import selected H.AVENUE lunch dates without rebuilding earlier menu results.

Run from any directory: python pipeline/import_selected_menus.py
The source page is read once per date. Existing rows and scores are preserved.
"""
import argparse
import hashlib
import io
import json
import re
import shutil
import tempfile
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path
from datetime import date as calendar_date, timedelta

from lxml import html
from PIL import Image, ImageOps

from auto_match import auto_match
from build_month import RAW_COMPONENT_NAMES, all_match_names, compute_tray, compute_tray_exchanges
from parse_month import parse_month_lunches, is_lunch_cat
from restore_menu_names import LABELS

ROOT = Path(__file__).resolve().parent.parent
DATES = [f'2026-10-{d:02d}' for d in range(26, 31)] + [f'2026-11-{d:02d}' for d in range(2, 7)]
SHOPS = {'105': ('s105', '학생식당'), '401': ('s401', '생활과학관식당'), '204': ('s204', '신소재공학관식당')}
BASE = 'https://fnb.hanyang.ac.kr'


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def write_json(path, value, indent=None):
    with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir=path.parent, suffix='.tmp', delete=False) as tmp:
        json.dump(value, tmp, ensure_ascii=False, indent=indent)
        tmp_path = Path(tmp.name)
    tmp_path.replace(path)


def fetch(url):
    request = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
    with urllib.request.urlopen(request, timeout=30) as response:
        return response.read()


def text(node, klass):
    return node.xpath(f'string(.//*[contains(concat(" ",normalize-space(@class)," ")," {klass} ")])').strip()


def scrape_day(date):
    source_url = f'{BASE}/front/fnbmMdMenu?date={date}'
    doc = html.fromstring(fetch(source_url).decode('utf-8'))
    day = {'date': date}
    for section in doc.xpath('//div[contains(concat(" ",normalize-space(@class)," ")," menu-slide-item ")]'):
        code = section.xpath('string(.//div[contains(@class,"round")]/span)').strip()
        if code not in SHOPS:
            continue
        skey, shop_name = SHOPS[code]
        items = []
        for li in section.xpath('.//ul[contains(@class,"menu-slide")]/li'):
            category = text(li, 'category')
            name = text(li, 'title')
            if not name or not is_lunch_cat(skey, category):
                continue
            styles = li.xpath('.//*[contains(@class,"thumb-img")]/@style')
            match = re.search(r'url\(["\']?([^"\')]+)', styles[0]) if styles else None
            image_url = urllib.parse.urljoin(BASE, match.group(1)) if match else None
            items.append({'category': category, 'name': name, 'desc': text(li, 'desc'),
                          'price': text(li, 'price'), 'img': image_url})
        day[skey] = {'shop': code, 'shopName': shop_name, 'items': items}
    if any(key not in day for key, _ in SHOPS.values()):
        raise ValueError(f'{date}: missing restaurant section')
    return day


def photo_key(row):
    key = f"{row['date']}_{row['shop']}_{row['category']}"
    return key + (f"#{row['cat_idx']}" if row.get('cat_idx') else '')


def to_site(row, photo):
    eu = row.get('식품교환단위')
    exchange = None
    if eu is not None:
        src = eu.get('매칭DB', {})
        exchange = {'grain': eu['곡류군'], 'meat': eu['어육류군'], 'veg': eu['채소군'],
                    'fat': eu['지방군'], 'dairy': eu['우유군'], 'fruit': eu['과일군'],
                    'unmatched': eu['미매칭_항목'], 'externalRecipes': eu.get('externalRecipes', []),
                    'recipeNotes': eu.get('recipeNotes', []),
                    'matchedDb': {'menugen': src.get('menugen', []), 'recipeDb': src.get('recipe_db', []),
                                  'db104': src.get('db104_direct', [])}}
    return {
        'date': row['date'], 'shop': row['shop'], 'shopName': row['shopName'],
        'category': row['category'], 'main': row['main'],
        'calculationMain': row.get('calculationMain', row['main']), 'price': row['price'],
        'photo': photo, 'weight': row['1인분_제공량_g'], 'kcal': row['kcal'],
        'protein': row['단백질_g'], 'fat': row['지방_g'], 'carb': row['탄수화물_g'],
        'sugar': row['당류_g'], 'fiber': row['식이섬유_g'], 'ca': row['칼슘_mg'], 'fe': row['철_mg'],
        'vitA': row['비타민A_ugRAE'], 'vitC': row['비타민C_mg'], 'satFat': row['포화지방_g'],
        'na': row['나트륨_mg'], 'nrf': row['NRF6.3'], 'confidence': row['신뢰도'],
        'unmatched': row['미매칭_항목'], 'gagongSourced': row['가공식품DB_출처_항목'],
        'components': [LABELS.get(name, name) for name in row['구성요소_목록']],
        'itemDetails': row.get('item_detail', []),
        'matchedDb': {'foodDb': row['영양_매칭DB'].get('food_db', []),
                      'recipeDecompose': row['영양_매칭DB'].get('recipe_decompose', []),
                      'gagongDb': row['영양_매칭DB'].get('gagong_db', [])},
        'exchangeUnits': exchange,
    }


def run(dates=None, source_file=None):
    requested_dates = DATES if dates is None else dates
    existing_source = read_json(ROOT / 'hanyang_menu_month.json')
    old_days = existing_source['days']
    old_site = read_json(ROOT / 'web/site_data.json')
    old_trays = read_json(ROOT / 'month_lunch_trays.json')
    old_parsed = read_json(ROOT / 'pipeline/month_lunch_parsed.json')
    photo_map = read_json(ROOT / 'photo_mapping.json')
    cache = read_json(ROOT / 'pipeline/master_cache.json')
    snapshot = read_json(ROOT / 'web/menu_exchange_snapshot.json')
    existing_dates = {row['date'] for row in old_days}
    if source_file:
        saved_days = {day['date']: day for day in read_json(Path(source_file))['days']}
        new_days = [saved_days[date] for date in requested_dates if date not in existing_dates]
    else:
        new_days = [scrape_day(date) for date in requested_dates if date not in existing_dates]
    if not new_days:
        from sync_allergy_data import sync_allergy_data
        sync_allergy_data()
        print('All requested dates already imported; menu data unchanged; allergy coverage checked.')
        return
    with tempfile.TemporaryDirectory(dir=ROOT.parent) as temp_dir:
        source_path = Path(temp_dir) / 'selected.json'
        write_json(source_path, {'days': new_days})
        lunches = parse_month_lunches(source_path)
    for day in new_days:
        count = Counter(row['shop'] for row in lunches if row['date'] == day['date'])
        expected = Counter({code: len(day[skey]['items']) for code, (skey, _) in SHOPS.items()})
        if not all(expected[code] for code in SHOPS):
            raise ValueError(f"{day['date']}: no published lunch menu for a restaurant")
        if count != expected:
            raise ValueError(f"{day['date']}: unexpected lunch counts {dict(count)}")
    existing_site_keys = {(x['date'], x['shop'], x['category'], x['main']) for x in old_site}
    if any((x['date'], x['shop'], x['category'], x['main']) in existing_site_keys for x in lunches):
        raise ValueError('An imported menu would overwrite an existing menu')

    new_names = sorted({name for lunch in lunches for name in all_match_names(lunch)} - cache.keys())
    print(f'New lunches: {len(lunches)}, new nutrient match names: {len(new_names)}', flush=True)
    for index, name in enumerate(new_names, 1):
        cache[name] = auto_match(name, prefer_db104=(name in RAW_COMPONENT_NAMES))
        if index % 25 == 0:
            print(f'  matched {index}/{len(new_names)}', flush=True)
    trays = [compute_tray(lunch, cache) for lunch in lunches]
    for tray in trays:
        if tray['shop'] in ('401', '204'):
            tray['식품교환단위'] = compute_tray_exchanges(
                tray['item_detail'], tray.get('calculationMain', tray['main']), tray['shop'], tray['date'])

    new_photos = {}
    for lunch in lunches:
        url = lunch.get('img')
        if not url:
            continue
        key = photo_key(lunch)
        if key in photo_map:
            continue
        try:
            raw = fetch(url)
            photo = ImageOps.exif_transpose(Image.open(io.BytesIO(raw))).convert('RGB')
            if photo.width > 800:
                photo = photo.resize((800, round(photo.height * 800 / photo.width)), Image.Resampling.LANCZOS)
            name = f"{hashlib.sha256(url.encode()).hexdigest()[:24]}.jpg"
            output = ROOT / 'menu_photos_web' / name
            photo.save(output, 'JPEG', quality=78)
            shutil.copy2(output, ROOT / 'web/menu_photos_web' / name)
            photo_map[key] = name
            new_photos[key] = name
        except Exception as exc:
            print(f'Photo unavailable {key}: {exc}', flush=True)

    new_site = [to_site(tray, photo_map.get(photo_key(tray))) for tray in trays]
    for lunch, tray, row in zip(lunches, trays, new_site):
        # Keep source menu titles separate from replacement recipe names.
        assert row['main'] == lunch['main']
        source_item = [item for item in next(day for day in new_days if day['date'] == lunch['date'])
                       ['s' + lunch['shop']]['items'] if item['category'] == lunch['category']][lunch.get('cat_idx', 0)]
        row['sourceMenuText'] = source_item['name']
        row['sourceUrl'] = f"{BASE}/front/fnbmMdMenu?date={lunch['date']}"
        tray['sourceMenuText'] = source_item['name']
    combined_site = sorted(old_site + new_site, key=lambda x:(x['date'], x['shop'], x['category'], x['main']))
    assert all(x in combined_site for x in old_site)
    source = dict(existing_source)
    source['days'] = sorted(old_days + new_days, key=lambda x:x['date'])
    source.setdefault('scraped_additional_ranges', []).append(
        {'start': min(day['date'] for day in new_days), 'end': max(day['date'] for day in new_days)})

    write_json(ROOT / 'hanyang_menu_month.json', source, 1)
    write_json(ROOT / 'pipeline/master_cache.json', cache, 1)
    write_json(ROOT / 'pipeline/month_lunch_parsed.json', old_parsed + lunches, 1)
    write_json(ROOT / 'month_lunch_trays.json', old_trays + trays, 1)
    write_json(ROOT / 'photo_mapping.json', photo_map, 1)
    write_json(ROOT / 'site_data.json', combined_site)
    write_json(ROOT / 'web/site_data.json', combined_site)
    keys = {tuple(entry['key']) for entry in snapshot['entries']}
    for row in new_site:
        key = (row['date'], row['shop'], row['category'], row['main'])
        if row['exchangeUnits'] is not None and key not in keys:
            snapshot['entries'].append({'key': list(key), 'sourceMain': row['main'],
                                        'exchangeUnits': row['exchangeUnits']})
    snapshot['sourceSha256'] = hashlib.sha256((ROOT / 'web/site_data.json').read_bytes()).hexdigest()
    write_json(ROOT / 'web/menu_exchange_snapshot.json', snapshot, 1)
    from sync_allergy_data import sync_allergy_data
    sync_allergy_data()
    summary = {'days':len(new_days), 'newMenus':len(new_site), 'byShop':dict(Counter(x['shop'] for x in new_site)),
               'photos':len(new_photos), 'withoutPhoto':sum(x['photo'] is None for x in new_site),
               'nutrientUnmatchedMenus':sum(bool(x['unmatched']) for x in new_site),
               'exchangeUnmatchedMenus':sum(bool(x['exchangeUnits']['unmatched']) for x in new_site)}
    print(json.dumps(summary, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--start', help='First date, YYYY-MM-DD')
    parser.add_argument('--end', help='Last date, YYYY-MM-DD')
    parser.add_argument('--source-file', help='Optional previously collected source JSON')
    args = parser.parse_args()
    if bool(args.start) != bool(args.end):
        parser.error('--start and --end must be provided together')
    dates = None
    if args.start:
        current, end = calendar_date.fromisoformat(args.start), calendar_date.fromisoformat(args.end)
        if current > end:
            parser.error('--start must not be after --end')
        dates = []
        while current <= end:
            if current.weekday() < 5:
                dates.append(current.isoformat())
            current += timedelta(days=1)
    run(dates, args.source_file)
