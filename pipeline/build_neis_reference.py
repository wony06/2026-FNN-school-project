"""Build an independent, source-traceable NEIS allergy reference (no website edits)."""
import argparse
import csv
import hashlib
import html
import json
import re
import sqlite3
import sys
import time
import unicodedata
from collections import Counter, defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path

from test_neis_api import api_key, request_rows

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / 'pipeline/_neis_cache'
OUT = ROOT / 'pipeline/neis_reference'
MONTHS = ('202609', '202610')
ALLERGENS = dict(enumerate([
    '난류', '우유', '메밀', '땅콩', '대두', '밀', '고등어', '게', '새우', '돼지고기',
    '복숭아', '토마토', '아황산류', '호두', '닭고기', '쇠고기', '오징어',
    '조개류(굴·전복·홍합 포함)', '잣'], 1))
NUMBER_GROUP = re.compile(r'[（(]\s*(\d+(?:\s*[.,．，]\s*\d+)*[.,．，]?)\s*[）)]')
ALIASES = {'돈까스': '돈가스', '치킨까스': '치킨가스', '생선까스': '생선가스'}


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()


def dump(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + '.tmp')
    temp.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding='utf-8')
    temp.replace(path)


def normalize_name(name):
    name = unicodedata.normalize('NFKC', name).casefold()
    name = re.sub(r'\s+', '', name).strip('*★☆')
    for old, new in ALIASES.items():
        name = name.replace(old, new)
    return name


def parse_dishes(raw):
    # HTML line breaks delimit dishes; '/', '&', ',' inside a name are NOT dish boundaries.
    lines = re.split(r'<br\s*/?>|[\r\n]+', raw, flags=re.I)
    for index, original in enumerate(lines):
        source = html.unescape(original).strip()
        if not source:
            continue
        numbers, review = set(), []
        valid_spans = []
        for match in NUMBER_GROUP.finditer(source):
            values = [int(n) for n in re.findall(r'\d+', match.group(1))]
            if all(n in ALLERGENS for n in values):
                numbers.update(values)
                valid_spans.append(match.span())
            else:
                review.append('OUT_OF_RANGE_NUMERIC_PARENTHESIS')
        name = source
        for start, end in reversed(valid_spans):
            name = name[:start] + name[end:]
        name = name.strip()
        # Unrecognized numeric annotations are preserved, never treated as an empty allergy set.
        name_for_review = unicodedata.normalize('NFKC', name)
        if re.search(r'\(\s*\d+(?:\s*[.,]\s*\d+)+', name_for_review) or re.search(r'\d+(?:\.\d+){2,}', name_for_review):
            review.append('UNPARSED_NUMERIC_ANNOTATION')
        status = '검토필요' if review else ('표기' if valid_spans else '미표기')
        yield {'line_index': index, 'source_text': source, 'original_menu_name': name,
               'normalized_menu_name': normalize_name(name), 'allergy_numbers': sorted(numbers),
               'allergy_names': [ALLERGENS[n] for n in sorted(numbers)],
               'label_status': status, 'review_flags': sorted(set(review))}


def cached_request(service, filename, key, offline=False, **filters):
    path = CACHE / filename
    if path.exists():
        cached = json.loads(path.read_text(encoding='utf-8'))
        if cached.get('filters') != filters or cached.get('service') != service:
            raise ValueError('Cache query mismatch')
        return cached['rows'], cached['fetched_at']
    if offline:
        raise ValueError('Required cache missing; collect with NEIS_API_KEY first')
    for attempt in range(3):
        try:
            rows = request_rows(service, key, **filters)
            timestamp = datetime.now(timezone.utc).isoformat()
            dump(path, {'service': service, 'filters': filters, 'fetched_at': timestamp, 'rows': rows})
            time.sleep(0.25)
            return rows, timestamp
        except RuntimeError:
            if attempt == 2:
                raise
            time.sleep(2 ** attempt)


def school_order(schools):
    # Reproducible geographic convenience sample; not a representative statistical sample.
    districts = defaultdict(list)
    unique = {}
    for school in schools:
        if school.get('ATPT_OFCDC_SC_CODE') != 'B10' or school.get('SCHUL_KND_SC_NM') != '고등학교':
            continue
        unique[school['SD_SCHUL_CODE']] = school
    for school in unique.values():
        address = school.get('ORG_RDNMA', '')
        match = re.search(r'서울특별시\s+(\S+구)', address)
        district = match.group(1) if match else '주소구분불명'
        districts[district].append(school)
    queues = {district: deque(sorted(rows, key=lambda r:(r['SCHUL_NM'], r['SD_SCHUL_CODE'])))
              for district, rows in sorted(districts.items())}
    while any(queues.values()):
        for district, queue in queues.items():
            if queue:
                yield district, queue.popleft()


def make_records(meals):
    unique_meals, duplicates = {}, 0
    for meal in meals:
        ident = [meal['ATPT_OFCDC_SC_CODE'], meal['SD_SCHUL_CODE'], meal['MLSV_YMD'],
                 meal['MMEAL_SC_CODE'], meal['DDISH_NM']]
        mid = digest(ident)
        if mid in unique_meals:
            duplicates += 1
        else:
            unique_meals[mid] = meal
    records = []
    for mid, meal in sorted(unique_meals.items(), key=lambda p:(p[1]['SD_SCHUL_CODE'],p[1]['MLSV_YMD'],p[1]['MMEAL_SC_CODE'],p[0])):
        for dish in parse_dishes(meal['DDISH_NM']):
            records.append({'record_id': digest([mid, dish['line_index']]), 'meal_id': mid,
                'school_name': meal['SCHUL_NM'], 'school_code': meal['SD_SCHUL_CODE'],
                'office_code': meal['ATPT_OFCDC_SC_CODE'], 'meal_date': meal['MLSV_YMD'],
                'meal_type_code': meal['MMEAL_SC_CODE'], 'meal_type': meal['MMEAL_SC_NM'],
                'DDISH_NM': meal['DDISH_NM'], 'fetched_at': meal['_fetched_at'], **dish})
    assert len({row['record_id'] for row in records}) == len(records)
    return records, duplicates, len(unique_meals)


def aggregate(records):
    groups = defaultdict(list)
    for row in records:
        groups[row['normalized_menu_name']].append(row)
    result = []
    for name, rows in sorted(groups.items()):
        valid = [row for row in rows if row['label_status'] == '표기']
        stats = []
        for code, food in ALLERGENS.items():
            marked = [row for row in valid if code in row['allergy_numbers']]
            stats.append({'number': code, 'name': food, 'labeled_school_count':len({r['school_code'] for r in marked}),
                          'labeled_record_count':len(marked), 'total_record_count':len(rows)})
        variants = defaultdict(list)
        for row in valid:
            variants[tuple(row['allergy_numbers'])].append(row)
        school_stats = []
        for school_code in sorted({row['school_code'] for row in rows}):
            school_rows = [r for r in rows if r['school_code']==school_code]
            school_stats.append({'school_code':school_code, 'school_name':school_rows[0]['school_name'],
                'record_count':len(school_rows), 'unlabeled_count':sum(r['label_status']=='미표기' for r in school_rows),
                'labeled_variants':sorted({tuple(r['allergy_numbers']) for r in school_rows if r['label_status']=='표기'})})
        result.append({'normalized_menu_name':name, 'original_names':sorted({r['original_menu_name'] for r in rows}),
            'record_count':len(rows), 'school_count':len(school_stats),
            'labeled_record_count':len(valid), 'unlabeled_record_count':sum(r['label_status']=='미표기' for r in rows),
            'review_record_count':sum(r['label_status']=='검토필요' for r in rows),
            'allergens':stats, 'schools':school_stats,
            'labeled_variants':[{'numbers':list(numbers), 'names':[ALLERGENS[n] for n in numbers],
                'record_count':len(items), 'school_count':len({r['school_code'] for r in items}),
                'record_ids':[r['record_id'] for r in items]}
                for numbers, items in sorted(variants.items())]})
    return result


def variation_examples(records, aggregates):
    by_name = defaultdict(list)
    for row in records:
        if row['label_status']=='표기':
            by_name[row['normalized_menu_name']].append(row)
    examples = []
    candidates = sorted(aggregates, key=lambda a:(-a['school_count'], -a['record_count'], a['normalized_menu_name']))
    for menu in candidates:
        if len(menu['labeled_variants']) < 2:
            continue
        rows = by_name[menu['normalized_menu_name']]
        pair = next(((a,b) for a in rows for b in rows
            if a['school_code']!=b['school_code'] and a['allergy_numbers']!=b['allergy_numbers']), None)
        if pair:
            examples.append({'normalized_menu_name':menu['normalized_menu_name'], 'records':list(pair)})
        if len(examples)==5:
            break
    return examples


def save_database(records, aggregates, schools):
    OUT.mkdir(parents=True, exist_ok=True)
    temp = OUT / 'reference.building.sqlite3'
    if temp.exists():
        temp.unlink()
    db = sqlite3.connect(temp)
    db.executescript('''PRAGMA foreign_keys=ON;
      CREATE TABLE schools(school_code TEXT PRIMARY KEY, school_name TEXT, office_code TEXT, metadata_json TEXT);
      CREATE TABLE allergens(number INTEGER PRIMARY KEY, name TEXT);
      CREATE TABLE records(record_id TEXT PRIMARY KEY, meal_id TEXT, school_code TEXT REFERENCES schools,
        meal_date TEXT, meal_type TEXT, original_menu_name TEXT, normalized_menu_name TEXT,
        label_status TEXT, source_text TEXT, source_json TEXT);
      CREATE TABLE record_allergens(record_id TEXT REFERENCES records, number INTEGER REFERENCES allergens,
        PRIMARY KEY(record_id,number));
      CREATE TABLE menu_aggregates(normalized_menu_name TEXT PRIMARY KEY, record_count INTEGER,
        school_count INTEGER, unlabeled_record_count INTEGER, review_record_count INTEGER, metadata_json TEXT);
      CREATE TABLE menu_allergen_stats(normalized_menu_name TEXT REFERENCES menu_aggregates,
        number INTEGER REFERENCES allergens, labeled_school_count INTEGER, labeled_record_count INTEGER,
        total_record_count INTEGER, PRIMARY KEY(normalized_menu_name,number));
      CREATE INDEX record_menu ON records(normalized_menu_name);
      CREATE INDEX record_school_date ON records(school_code,meal_date);
    ''')
    db.executemany('INSERT INTO allergens VALUES (?,?)', ALLERGENS.items())
    db.executemany('INSERT INTO schools VALUES (?,?,?,?)', [(s['SD_SCHUL_CODE'],s['SCHUL_NM'],s['ATPT_OFCDC_SC_CODE'],
        json.dumps(s,ensure_ascii=False)) for s in schools])
    db.executemany('INSERT INTO records VALUES (?,?,?,?,?,?,?,?,?,?)', [(r['record_id'],r['meal_id'],r['school_code'],
        r['meal_date'],r['meal_type'],r['original_menu_name'],r['normalized_menu_name'],r['label_status'],r['source_text'],
        json.dumps(r,ensure_ascii=False)) for r in records])
    db.executemany('INSERT INTO record_allergens VALUES (?,?)', [(r['record_id'],n) for r in records
        if r['label_status']=='표기' for n in r['allergy_numbers']])
    db.executemany('INSERT INTO menu_aggregates VALUES (?,?,?,?,?,?)', [(a['normalized_menu_name'],a['record_count'],a['school_count'],
        a['unlabeled_record_count'],a['review_record_count'],json.dumps(a,ensure_ascii=False)) for a in aggregates])
    db.executemany('INSERT INTO menu_allergen_stats VALUES (?,?,?,?,?)', [(a['normalized_menu_name'],s['number'],
        s['labeled_school_count'],s['labeled_record_count'],s['total_record_count']) for a in aggregates for s in a['allergens']])
    db.commit()
    assert db.execute('PRAGMA integrity_check').fetchone()[0]=='ok'
    assert not db.execute('PRAGMA foreign_key_check').fetchall()
    assert db.execute('SELECT COUNT(*) FROM records').fetchone()[0]==len(records)
    db.close()
    temp.replace(OUT/'reference.sqlite3')


def run(offline=False):
    key = None if offline else api_key()
    schools, _ = cached_request('schoolInfo','schools_seoul_high.json',key,offline,
        ATPT_OFCDC_SC_CODE='B10', SCHUL_KND_SC_NM='고등학교')
    selected, collected, attempts = [], [], []
    for district, school in school_order(schools):
        month_rows, counts = [], {}
        for month in MONTHS:
            end = '30' if month.endswith('09') else '31'
            rows, fetched = cached_request('mealServiceDietInfo',f"{school['SD_SCHUL_CODE']}_{month}.json",key,offline,
                ATPT_OFCDC_SC_CODE='B10', SD_SCHUL_CODE=school['SD_SCHUL_CODE'],
                MLSV_FROM_YMD=month+'01', MLSV_TO_YMD=month+end)
            for row in rows:
                if (row['SD_SCHUL_CODE']!=school['SD_SCHUL_CODE'] or row['ATPT_OFCDC_SC_CODE']!='B10'
                    or not row['MLSV_YMD'].startswith(month) or not isinstance(row.get('DDISH_NM'),str)):
                    raise ValueError('API source scope validation failed')
            month_rows.extend(dict(row,_fetched_at=fetched) for row in rows)
            counts[month]=len(rows)
        accepted = all(counts.values())
        attempts.append({'school_name':school['SCHUL_NM'],'school_code':school['SD_SCHUL_CODE'],
                         'district':district,'monthly_meal_counts':counts,'accepted':accepted})
        if accepted:
            selected.append(school)
            collected.extend(month_rows)
            print(f"{len(selected)}/20 {school['SCHUL_NM']}: {counts}",flush=True)
        if len(selected)==20:
            break
    if len(selected)!=20:
        raise ValueError(f'Both months available for only {len(selected)} schools; no complete DB published')
    records, duplicates, meal_count = make_records(collected)
    aggregates = aggregate(records)
    examples = variation_examples(records,aggregates)
    summary = {'generated_at':datetime.now(timezone.utc).isoformat(), 'months':list(MONTHS),
        'school_count':len(selected),'meal_rows_received':len(collected),'duplicate_meal_rows_removed':duplicates,
        'unique_meal_count':meal_count,'menu_record_count':len(records),
        'unique_original_menu_count':len({r['original_menu_name'] for r in records}),
        'unique_normalized_menu_count':len(aggregates),
        'label_status_counts':dict(Counter(r['label_status'] for r in records)),
        'cross_school_variant_menu_count':sum(a['school_count']>1 and len(a['labeled_variants'])>1 for a in aggregates),
        'school_selection_attempts':attempts,'variation_examples':examples,
        'normalization_version':'conservative-v1','meal_scope':'조식·중식·석식 등 API가 반환한 모든 급식구분',
        'interpretation':'미표기/어떤 번호의 비표시는 부재나 안전의 증거가 아님. 다른 학교 메뉴의 표시를 한양대 메뉴의 확정 알레르기로 적용하지 않음.'}
    assert sum(a['record_count'] for a in aggregates)==len(records)
    assert len(examples)==5, 'Five cross-school labeled variation examples required'
    save_database(records,aggregates,selected)
    dump(OUT/'schools.json', selected)
    dump(OUT/'menu_aggregates.json',aggregates)
    dump(OUT/'summary.json',summary)
    with (OUT/'records.jsonl').open('w',encoding='utf-8',newline='\n') as output:
        for record in records:
            output.write(json.dumps(record,ensure_ascii=False)+'\n')
    with (OUT/'allergen_stats.csv').open('w',encoding='utf-8-sig',newline='') as output:
        writer=csv.writer(output)
        writer.writerow(['정규화메뉴명','메뉴전체기록수','메뉴학교수','미표기기록수','검토기록수','알레르기번호','알레르기명','표시학교수','표시기록수'])
        for a in aggregates:
            for stat in a['allergens']:
                writer.writerow([a['normalized_menu_name'],a['record_count'],a['school_count'],a['unlabeled_record_count'],
                    a['review_record_count'],stat['number'],stat['name'],stat['labeled_school_count'],stat['labeled_record_count']])
    lines=['# NEIS 알레르기 참고 DB 수집 결과','',f"서울 고등학교 {len(selected)}개, 2026년 9~10월, 모든 급식구분.",
        f"급식 {meal_count}건 / 개별 메뉴 {len(records)}건 / 정규화 후 메뉴 {len(aggregates)}종.",
        f"표기 상태: {summary['label_status_counts']}",'','## 학교 간 표시 차이 사례','']
    for example in examples:
        lines.append('### '+example['normalized_menu_name'])
        for row in example['records']:
            lines.append(f"- {row['school_name']} {row['meal_date']} {row['meal_type']}: {row['source_text']} → {', '.join(row['allergy_names'])}")
        lines.append('')
    lines.extend(['표시 차이는 배합·제품·학교별 입력 차이일 수 있으며 어느 쪽의 오류 또는 특정 성분 부재를 확정하지 않습니다.',
        '미표기는 알레르기 성분 없음으로 해석하지 않습니다. 한양대 메뉴 및 추천에는 연결하지 않았습니다.'])
    (OUT/'REPORT.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in summary.items() if k not in ('variation_examples','school_selection_attempts')},ensure_ascii=False,indent=2))
    print(f'Output: {OUT}',flush=True)


if __name__=='__main__':
    if hasattr(sys.stdout,'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    parser=argparse.ArgumentParser()
    parser.add_argument('--from-cache',action='store_true',help='Rebuild from downloaded data without any API key or network access')
    args=parser.parse_args()
    try:
        run(args.from_cache)
    except (ValueError,RuntimeError) as error:
        print(str(error),file=sys.stderr)
        sys.exit(1)
