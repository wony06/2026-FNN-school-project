"""Classify potential allergens from source-supported names and exact NEIS name matches.

This is an independent analysis. No confirmed presence/absence, safety, or filter is produced.
"""
import csv
import hashlib
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from build_neis_reference import ALLERGENS, normalize_name
from match_hyu_neis import contains_source, name_evidence

ROOT=Path(__file__).resolve().parent.parent
INPUT=ROOT/'pipeline/hyu_neis_matching'
OUT=ROOT/'pipeline/hyu_allergy_estimates'
LABELS={'name_and_neis_possible':'메뉴명단서·NEIS포함가능','name_indicated':'메뉴명단서',
        'neis_possible':'NEIS포함가능','unknown':'확인불가'}
SHOP={'105':'한양플라자','401':'생활과학대학','204':'신소재공학관'}


def load(path):return json.loads(path.read_text(encoding='utf-8'))
def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def run():
    protected=[ROOT/'web/site_data.json',ROOT/'month_lunch_trays.json',ROOT/'hanyang_menu_month.json',
        ROOT/'web/index.html',ROOT/'web/modern.css',ROOT/'web/personal-score.js',ROOT/'web/instant-rice.js',
        ROOT/'pipeline/neis_reference/reference.sqlite3',INPUT/'meal_matches.json']
    before={str(p.relative_to(ROOT)):sha(p) for p in protected}
    meals=load(INPUT/'meal_matches.json')
    aggregates=load(INPUT/'reference_evidence.json')
    records=[json.loads(line) for line in (INPUT/'evidence_records.jsonl').read_text(encoding='utf-8').splitlines()]
    sources={r['record_id']:r for r in records}
    code_records=defaultdict(list)
    for r in records:
        if r['label_status']=='표기':
            for code in r['allergy_numbers']:code_records[(r['normalized_menu_name'],code)].append(r['record_id'])
    output=[]
    excluded_total=0
    for meal in meals:
        source_text=meal.get('source_menu_text') or ''
        # SELF notices contain a slash unrelated to food choices; remove that notice for this check.
        choice_text=re.split(r'샐러드&토핑&드레싱|\(self\)',source_text,flags=re.I)[0]
        ambiguous_choice=bool(re.search(r'\bor\b|또는|선택|/',choice_text,flags=re.I))
        components=[]
        excluded=[]
        for part in meal['component_results']:
            if not part['source_name_supported'] or part['result'] is None:
                excluded.append({'index':part['component_index'],'name':part.get('calculation_only_query'),
                    'reason':'계산용 가정·대체·분해 또는 원문 미확인: 알레르기 근거에서 완전히 제외'})
                continue
            components.append({'component_id':f"component-{part['component_index']}",
                'source_scope':'원문에 등장하는 구성 메뉴명','match':part['result']})
        excluded_total+=len(excluded)
        main=meal['main_result']
        if (contains_source(meal.get('source_menu_text') or '',main['query'])
            and not any(normalize_name(c['match']['query'])==normalize_name(main['query']) for c in components)):
            components.insert(0,{'component_id':'original-main','source_scope':'원문에 등장하는 메인명; 계산용 대체 이름 아님','match':main})
        per_component=[]
        for c in components:
            m=c['match']
            named=name_evidence(m['query'])
            accepted=m['match_type'] in ('exact','synonym')
            ref=m['reference_menu'] if accepted else None
            neis=[]
            if ref:
                a=aggregates[ref]
                for stat in a['allergens']:
                    if stat['labeled_record_count']:
                        ids=sorted(set(code_records[(ref,stat['number'])]))
                        assert len(ids)==stat['labeled_record_count']
                        neis.append({**stat,'reference_menu':ref,'source_record_ids':ids,
                            'meaning':'다른 학교 동일 명칭의 표시 근거; 한양대 실제 성분 미확인'})
            per_component.append({'component_id':c['component_id'],'name':m['query'],'source_scope':c['source_scope'],
                'integration_applied':not ambiguous_choice,
                'match_type':m['match_type'],'reference_menu':ref,'name_indications':named,'neis_possible':neis,
                'unresolved':{'actual_recipe_unknown':True,'unlabeled_reference_records':aggregates[ref]['unlabeled_record_count'] if ref else None,
                    'review_reference_records':aggregates[ref]['review_record_count'] if ref else None,
                    'no_confirmed_reference_match':not accepted,
                    'review_candidates_not_applied':m['candidates'] if not accepted else []}})
        statuses=[]
        for number,food in ALLERGENS.items():
            named=[];neis=[]
            for c in per_component:
                if not c['integration_applied']:continue
                for item in c['name_indications']:
                    if item['number']==number:
                        named.append({'component_id':c['component_id'],'component_name':c['name'],**item})
                for item in c['neis_possible']:
                    if item['number']==number:
                        neis.append({'component_id':c['component_id'],'component_name':c['name'],**item})
            kind='name_and_neis_possible' if named and neis else 'name_indicated' if named else 'neis_possible' if neis else 'unknown'
            source_ids=sorted({rid for item in neis for rid in item['source_record_ids']})
            statuses.append({'number':number,'name':food,'classification':kind,
                'name_evidence':named,'neis_evidence':neis,'supporting_source_record_ids':source_ids,
                'distinct_supporting_record_count':len(source_ids),
                'distinct_supporting_school_count':len({sources[rid]['school_code'] for rid in source_ids}),
                'hyu_actual_presence':'확인불가','absence_confirmed':False,
                'unknown_reason':'실제 한양대 원재료·제품·조리배합 미확인. 번호 비표시는 부재 또는 안전 근거가 아님.'})
        output.append({'meal_key':meal['meal_key'],'shop_name':SHOP[meal['meal_key'][1]],
            'source_menu_text':meal['source_menu_text'],'allergens':statuses,'components':per_component,
            'excluded_calculation_components':excluded,
            'unknowns':{'actual_recipe_unknown':True,'source_component_boundaries_need_review':True,
                'choice_or_separator_integration_withheld':ambiguous_choice,
                'source_coverage_not_guaranteed':True,
                'excluded_calculation_component_count':len(excluded),
                'components_without_reference_match':[c['name'] for c in per_component if c['unresolved']['no_confirmed_reference_match']],
                'meaning':'통합은 포함 가능 근거의 합집합이며 실제 식단의 확정 성분표가 아님. 숨은 재료·미확인 구성은 남아 있음.'}})
    expected_excluded=load(INPUT/'summary.json')['calculation_only_component_occurrences']
    assert excluded_total==expected_excluded
    assert len(output)==len(meals) and all(len(row['allergens'])==19 for row in output)
    wanted=['고구마치즈돈까스','등심돈까스','제육덮밥','차돌순두부찌개','수육','감자탕','계란볶음밥',
        '마라샹궈','설렁탕&소면사리','가라아게덮밥','간장돈육볶음','고추참치마요덮밥','곰탕',
        '김치찌개&라면사리','하와이안함박스테이크','냉모밀','우삼겹하이라이스','돼지고기애호박찌개',
        '날치알김치볶음밥','돈까스나베']
    examples=[]
    for name in wanted:
        candidates=[r for r in output if r['meal_key'][3]==name]
        if candidates:examples.append(candidates[0])
    seen={r['meal_key'][3] for r in examples}
    # Ensure all three restaurants occur, then fill any absent names from real data.
    for shop in SHOP:
        if not any(r['meal_key'][1]==shop for r in examples):
            extra=next(r for r in output if r['meal_key'][1]==shop and r['meal_key'][3] not in seen)
            if len(examples)==20:examples.pop()
            examples.append(extra);seen.add(extra['meal_key'][3])
    for r in output:
        if len(examples)>=20:break
        if r['meal_key'][3] not in seen:examples.append(r);seen.add(r['meal_key'][3])
    assert len(examples)==20
    summary={'meal_count':len(output),'excluded_calculation_component_occurrences':excluded_total,
        'source_supported_components_analyzed':sum(len(r['components']) for r in output),
        'classification_counts':dict(Counter(a['classification'] for r in output for a in r['allergens'])),
        'meals_with_name_evidence':sum(any(a['name_evidence'] for a in r['allergens']) for r in output),
        'meals_with_neis_evidence':sum(any(a['neis_evidence'] for a in r['allergens']) for r in output),
        'meals_with_unknown_recipe':len(output),'source_evidence_records':len(records),'protected_sha256':before}
    summary['choice_or_separator_integration_withheld_meals']=sum(r['unknowns']['choice_or_separator_integration_withheld'] for r in output)
    OUT.mkdir(parents=True,exist_ok=True)
    for filename,data in [('meal_estimates.json',output),('examples20.json',examples),('summary.json',summary),
                          ('reference_statistics.json',aggregates)]:
        (OUT/filename).write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    with (OUT/'source_records.jsonl').open('w',encoding='utf-8') as f:
        for r in records:f.write(json.dumps(r,ensure_ascii=False)+'\n')
    with (OUT/'meal_allergen_estimates.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.writer(f);w.writerow(['날짜','식당','메인명','알레르기번호','식품명','분류','메뉴명근거','NEIS근거구성메뉴',
            '근거기록수_중복제거','근거학교수_중복제거','실제배합확인'])
        for r in output:
            for a in r['allergens']:
                w.writerow([r['meal_key'][0],r['shop_name'],r['meal_key'][3],a['number'],a['name'],LABELS[a['classification']],
                    ' / '.join(x['component_name'] for x in a['name_evidence']),
                    ' / '.join(x['component_name'] for x in a['neis_evidence']),
                    a['distinct_supporting_record_count'],a['distinct_supporting_school_count'],'확인불가'])
    lines=['# 한양대 알레르기 유발 가능성 추정','',
        '모든 판정은 참고용 추정이다. 메뉴명 단서도 실제 원재료·제품 확인을 의미하지 않는다.',
        '미표기·특정 번호 비표시는 성분 부재/안전으로 해석하지 않는다. 필터와 UI에는 연결하지 않았다.',
        f'식단 {len(output)}개, 계산용 구성요소 {excluded_total}회 제외.','',
        '|날짜·식당|메인명|메뉴명 단서(번호)|NEIS 포함 가능(번호)|', '|---|---|---|---|']
    for r in examples:
        named=[str(a['number']) for a in r['allergens'] if a['name_evidence']]
        neis=[str(a['number']) for a in r['allergens'] if a['neis_evidence']]
        name_text=', '.join(named) or '없음(부재 아님)'
        neis_text=', '.join(neis) or '동일명 근거 없음'
        if r['unknowns']['choice_or_separator_integration_withheld']:
            name_text=neis_text='통합 보류(구성별 근거 별도 보존)'
        lines.append(f"|{r['meal_key'][0]} {r['shop_name']}|{r['meal_key'][3]}|{name_text}|{neis_text}|")
    lines.extend(['','## 사례별 근거 및 출처',''])
    for r in examples:
        lines.append('### '+r['meal_key'][3]+' / '+r['meal_key'][0]+' / '+r['shop_name'])
        for c in r['components']:
            named=', '.join(a['name'] for a in c['name_indications']) or '없음'
            lines.append(f"- 구성 메뉴 **{c['name']}** [{c['match_type']}]: 메뉴명 단서 {named}")
            for a in c['neis_possible']:
                record=sources[a['source_record_ids'][0]]
                lines.append(f"  - {a['number']} {a['name']}: {a['labeled_school_count']}학교 / {a['labeled_record_count']}표시기록 / {a['total_record_count']}전체기록. 예: {record['school_name']} {record['meal_date']} {record['source_text']} / ID {record['record_id']}")
        lines.append('제외 구성요소: '+', '.join(x['name'] or '' for x in r['excluded_calculation_components']))
        lines.append('동일명 근거 없는 구성 메뉴: '+', '.join(r['unknowns']['components_without_reference_match']))
        if r['unknowns']['choice_or_separator_integration_withheld']:
            lines.append('선택형(or/또는/선택) 또는 슬래시 구분 의미 미확인: 구성별 후보 근거는 보존하되 식단 통합은 보류.')
        lines.append('실제 배합·제품 및 원문의 구성 경계는 추가 확인이 필요하다.\n')
    lines.extend(['## 과도한 추정·누락 위험','',
        '- 국·튀김에서 소스·조미료 때문에 다른 학교의 쇠고기·조개류 등이 표시될 수 있다. 그대로 확정하면 과도한 경고가 된다. 빈도가 낮아도 포함 가능 근거는 보존한다.',
        '- 이름에 재료가 드러나지 않는 마요네즈·국수·빵·양념 등에서 숨은 성분이 누락될 수 있다. 이름만으로 난류·밀·대두를 일괄 추론하지 않는다.',
        '- 계산용으로 붙였던 밥·소스·토핑을 제외했기 때문에 실제 제공된 소스가 원문에서 생략됐다면 분석도 빠질 수 있다. 실제 제공량·제품 라벨 확인이 필요하다.',
        '- 유사한 이름 후보는 성분 통합에 사용하지 않았다. 가라아게덮밥/치킨가라아게, 곰탕/닭곰탕 등은 동일 메뉴로 확정하지 않는다.',
        '- 한 끼 근거 기록 수는 record_id로 중복 제거하며 서로 다른 음식의 학교·기록 수를 단순 합산하지 않는다. 메뉴별 원래 분모와 출처는 별도로 유지한다.',
        '- 원문 지지 여부는 텍스트 확인이며 실물·선택형(or)·공통 반찬 제공 여부가 완전히 검증된 것은 아니다. 모든 식단의 실제 배합은 확인불가다.'])
    (OUT/'REPORT.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    assert all(sha(p)==before[str(p.relative_to(ROOT))] for p in protected)
    print(json.dumps(summary,ensure_ascii=False,indent=2))


if __name__=='__main__':
    import sys
    if hasattr(sys.stdout,'reconfigure'):sys.stdout.reconfigure(encoding='utf-8')
    run()
