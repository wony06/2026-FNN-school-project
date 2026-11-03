"""Read-only HYU/NEIS comparison. Never joins allergy codes at meal level."""
import csv
import hashlib
import json
import re
import sqlite3
import unicodedata
from collections import Counter, defaultdict
from difflib import SequenceMatcher
from pathlib import Path

from build_neis_reference import ALLERGENS, normalize_name

ROOT=Path(__file__).resolve().parent.parent
OUT=ROOT/'pipeline/hyu_neis_matching'
STATUS={'exact':'완전일치','synonym':'표기동의어','review':'검토필요','unmatched':'미매칭'}
NAME_CUES={1:('계란','달걀','메추리알'),2:('우유','치즈','요거트','요구르트','버터'),3:('메밀',),
 4:('땅콩',),5:('대두','두부','콩나물','유부','두유'),7:('고등어',),8:('꽃게','대게','홍게','게살'),
 9:('새우',),10:('돼지','돈육','제육'),11:('복숭아',),12:('토마토',),14:('호두',),
 15:('닭','치킨'),16:('소고기','쇠고기','우삼겹','차돌박이'),17:('오징어',),
 18:('전복','홍합','바지락','조개','꼬막','가리비','굴'),19:('잣',)}


def load(path): return json.loads(path.read_text(encoding='utf-8'))
def sha(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def literal_key(name): return unicodedata.normalize('NFKC',name).strip()
def menu_key(row): return (row['date'],row['shop'],row['category'],row['main'])


def name_evidence(name):
    key=normalize_name(name)
    # 게맛살 is an imitation product; its name does not directly confirm crab.
    key=key.replace('게맛살','맛살').replace('굴림만두','만두')
    return [{'number':n,'name':ALLERGENS[n],'matched_terms':[cue for cue in cues if cue in key],
             'basis':'메뉴명 명시 단서; 실제 원재료/제품 확인 아님'}
            for n,cues in NAME_CUES.items() if any(cue in key for cue in cues)]


def contains_source(raw,name):
    if not name: return False
    return bool(re.search(r'(?<![가-힣A-Za-z0-9])'+re.escape(name)+r'(?![가-힣A-Za-z0-9])',raw))


def run():
    protected=[ROOT/'web/site_data.json',ROOT/'hanyang_menu_month.json',ROOT/'month_lunch_trays.json',
               ROOT/'pipeline/neis_reference/reference.sqlite3']
    before={str(p.relative_to(ROOT)):sha(p) for p in protected}
    meals=load(ROOT/'web/site_data.json')
    assert all(row['shop'] in ('105','401','204') for row in meals)
    db=sqlite3.connect((ROOT/'pipeline/neis_reference/reference.sqlite3').as_uri()+'?mode=ro',uri=True)
    ref={name:json.loads(meta) for name,meta in db.execute('SELECT normalized_menu_name,metadata_json FROM menu_aggregates')}
    raw_index={}
    for name,entry in ref.items():
        for original in entry['original_names']:
            raw_index[literal_key(original)]=name
    parsed=defaultdict(list)
    for row in load(ROOT/'pipeline/month_lunch_parsed.json'):
        parsed[(row['date'],row['shop'],row['category'])].append(row)
    raw_sources={}
    for day in load(ROOT/'hanyang_menu_month.json')['days']:
        for shop in ('105','401','204'):
            counts=Counter()
            for item in day.get('s'+shop,{}).get('items',[]):
                category=item['category']; idx=counts[category]; counts[category]+=1
                raw_sources[(day['date'],shop,category,idx)]=item
    memo={}
    def match(name):
        if name in memo: return memo[name]
        normalized=normalize_name(name)
        if literal_key(name) in raw_index:
            kind,target='exact',raw_index[literal_key(name)]
        elif normalized in ref:
            kind,target='synonym',normalized
        else:
            kind,target='unmatched',None
        candidates=[]
        if target is None and len(normalized)>=2:
            for candidate in ref:
                if len(candidate)<2: continue
                if not (set(candidate)&set(normalized)): continue
                ratio=SequenceMatcher(None,normalized,candidate,autojunk=False).ratio()
                overlap=len(set(candidate)&set(normalized))
                if ratio>=0.65 and overlap>=2:
                    candidates.append({'reference_menu':candidate,'similarity':round(ratio,4),
                        'reason':'문자열 유사도 후보; 재료·조리법 일치 미확인, 알레르기 코드 미적용'})
            candidates=sorted(candidates,key=lambda x:(-x['similarity'],x['reference_menu']))[:5]
            if candidates: kind='review'
        stats=ref[target] if target else None
        memo[name]={'query':name,'normalized_query':normalized,'match_type':kind,'reference_menu':target,
            'candidates':candidates,'name_explicit_ingredients':name_evidence(name),
            'neis_possible_ingredients':[{**stat,'evidence_reference_menu':target}
                for stat in stats['allergens'] if stat['labeled_record_count']>0] if stats else [],
            'unknown':{'unlabeled_record_count':stats['unlabeled_record_count'] if stats else None,
                'review_record_count':stats['review_record_count'] if stats else None,
                'actual_hyu_ingredients_verified':False,
                'meaning':'미표기·특정 번호의 비표시는 부재 근거가 아님. 실제 한양대 배합·제품은 확인 불가.'}}
        return memo[name]

    output=[]
    for index,meal in enumerate(meals):
        options=parsed.get((meal['date'],meal['shop'],meal['category']),[])
        exact=[r for r in options if r['main']==meal['main']]
        source=exact[0] if len(exact)==1 else (options[0] if len(options)==1 else None)
        raw=meal.get('sourceMenuText','')
        parts=[]
        if source:
            # Preserve the existing parser's dish boundaries; do not split composite names again.
            original=raw_sources.get((meal['date'],meal['shop'],meal['category'],source.get('cat_idx',0)),{})
            raw=' '.join([original.get('name',''),original.get('desc','')]).strip() or raw
            parts=[(name,contains_source(raw,name),'existing_lunch_parser_checked_against_raw_menu')
                for name in [source['main'],*source['sides']]]
        else:
            parts=[(name,contains_source(raw,name),'existing_components_checked_against_source_text')
                   for name in meal.get('components',[])]
        component_results=[]
        for component_index,(name,verified,origin) in enumerate(parts):
            result=match(name)
            component_results.append({'component_index':component_index,'source_name_supported':verified,
                'source_origin':origin,'result':result if verified else None,
                'calculation_only_query':name if not verified else None,
                'review_reason':None if verified else '계산용 대체/분해/추가 항목일 수 있어 실제 메뉴로 확정하지 않음'})
        output.append({'meal_key':list(menu_key(meal)),'row_index':index,'shop_name':meal['shopName'],
            'main_result':match(meal['main']),'main_result_scope':'메인명만의 비교이며 한 끼 식단 전체의 알레르기가 아님',
            'source_menu_text':raw or None,'parsed_source':source,'component_results':component_results,
            'meal_allergen_union':None,'meal_allergen_union_reason':'구성 경계·실제 배합 미확인: 알레르기 코드 자동 합산 안함'})

    OUT.mkdir(parents=True,exist_ok=True)
    targets={m['reference_menu'] for m in memo.values() if m['reference_menu']}
    evidence=[]
    for raw_json, in db.execute('SELECT source_json FROM records'):
        record=json.loads(raw_json)
        if record['normalized_menu_name'] in targets: evidence.append(record)
    db.close()
    unique_main={row['main'] for row in meals}
    source_components=[c['result'] for row in output for c in row['component_results'] if c['result']]
    main_counts=Counter(row['main_result']['match_type'] for row in output)
    component_counts=Counter(c['match_type'] for c in source_components)
    successful=[]
    ambiguous=[]
    seen=set()
    for row in output:
        result=row['main_result']
        if result['query'] in seen:continue
        seen.add(result['query'])
        example={'meal_key':row['meal_key'],'shop_name':row['shop_name'],'result':result}
        if result['match_type'] in ('exact','synonym'):successful.append(example)
        elif result['match_type']=='review':ambiguous.append(example)
    # Mix exact and spelling-alias examples rather than only the most frequent dishes.
    successful=sorted(successful,key=lambda r:(r['result']['match_type']!='synonym',r['result']['query']))[:10]
    ambiguous=sorted(ambiguous,key=lambda r:r['result']['query'])[:10]
    summary={'meal_rows':len(meals),'unique_main_names':len(unique_main),
        'meal_main_match_counts':{STATUS[k]:main_counts[k] for k in STATUS},
        'unique_main_match_counts':dict(Counter(STATUS[match(n)['match_type']] for n in unique_main)),
        'source_supported_component_occurrences':len(source_components),
        'component_match_counts':{STATUS[k]:component_counts[k] for k in STATUS},
        'calculation_only_component_occurrences':sum(c['result'] is None for r in output for c in r['component_results']),
        'reference_evidence_records':len(evidence),'successful_examples':successful,'ambiguous_examples':ambiguous,
        'input_sha256':before,'count_scope':'식단 행 수 기준 메인명 비교; 구성 메뉴의 매칭은 별도 집계',
        'interpretation':'명칭 일치만 확정. 한양대 실물의 성분은 확정하지 않음. 후보 성분은 미적용.'}
    assert sum(main_counts.values())==len(meals)
    assert len({tuple(r['meal_key']) for r in output})==len(output)
    assert all(before[str(p.relative_to(ROOT))]==sha(p) for p in protected)
    for name,value in [('meal_matches.json',output),('name_matches.json',memo),('summary.json',summary),
                       ('reference_evidence.json',{key:ref[key] for key in sorted(targets)})]:
        (OUT/name).write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
    with (OUT/'evidence_records.jsonl').open('w',encoding='utf-8') as f:
        for record in evidence:f.write(json.dumps(record,ensure_ascii=False)+'\n')
    with (OUT/'main_matches.csv').open('w',encoding='utf-8-sig',newline='') as f:
        w=csv.writer(f);w.writerow(['날짜','식당코드','식당','구분','메인명','분류','NEIS정규화명','검토후보'])
        for r in output:
            w.writerow([r['meal_key'][0],r['meal_key'][1],r['shop_name'],r['meal_key'][2],r['meal_key'][3],
                STATUS[r['main_result']['match_type']],r['main_result']['reference_menu'],
                ' / '.join(x['reference_menu'] for x in r['main_result']['candidates'])])
    lines=['# 한양대–NEIS 알레르기 참고 매칭 결과','',
        '이 분석은 메뉴명 비교이며 실제 한양대 음식의 원재료 확인이나 알레르기 필터가 아니다.',
        '메인명 결과는 한 끼 전체에 적용하지 않으며, 구성 메뉴별로 따로 저장한다.','',
        f"식단 {len(meals)}행 / 고유 메인명 {len(unique_main)}종.",
        f"식단 메인명 분류: {summary['meal_main_match_counts']}",
        f"원문 지지 구성 메뉴 {len(source_components)}회: {summary['component_match_counts']}",
        f"계산용 또는 원문으로 확인되지 않은 구성요소 {summary['calculation_only_component_occurrences']}회는 적용 보류.",
        '', '## 명칭 매칭 성공 사례 10개','']
    for x in successful:
        r=x['result']; a=ref[r['reference_menu']]
        original=next(z for z in evidence if z['normalized_menu_name']==r['reference_menu'])
        lines.extend([f"### {r['query']} → {r['reference_menu']} ({STATUS[r['match_type']]})",
            f"- 한양대: {x['meal_key'][0]} / {x['shop_name']} / {x['meal_key'][2]}",
            f"- NEIS: {original['school_name']} / {original['meal_date']} / {original['source_text']}",
            f"- 참조 기록 {a['record_count']}회, 학교 {a['school_count']}개, 미표기 {a['unlabeled_record_count']}회",''])
    lines.extend(['## 검토 후보 사례 10개',''])
    for x in ambiguous:
        r=x['result']
        lines.append(f"- {x['meal_key'][0]} {x['shop_name']} **{r['query']}** → 후보: "+
            ' / '.join(c['reference_menu'] for c in r['candidates'])+' (성분 미적용)')
    lines.extend(['','## 검토할 문제점','',
        '- 단순 유사도에는 제육/멸치, 양념 차이, 덮밥/단품 같은 부적절한 후보도 포함된다. 자동 확정하지 않는다.',
        '- 동일 명칭이어도 학교별 배합·제품·표시 차이가 있어 다수결로 성분 부재를 판단하지 않는다.',
        '- 기존 구성요소에는 원본에 없는 대체 음식·레시피 분해·가정 추가 반찬이 있어 원문 확인이 필요하다.',
        '- 원문에 등장하는 구성요소라도 원래 파서의 분리 오류 가능성이 남아 있다. 복합명을 추가 분해하지 않았다.',
        '- 메뉴명 명시 단서는 실제 원재료 확인과 다르다. 포괄명(김치·샐러드·소스 등)은 추가 세부 확인이 필요하다.',
        '- 미표기·검토필요는 별도 보존한다. 미표기 및 어떤 번호의 비표시는 음성 근거가 아니다.'])
    (OUT/'REPORT.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps({k:v for k,v in summary.items() if not k.endswith('_examples')},ensure_ascii=False,indent=2))


if __name__=='__main__':
    import sys
    if hasattr(sys.stdout,'reconfigure'):sys.stdout.reconfigure(encoding='utf-8')
    run()
