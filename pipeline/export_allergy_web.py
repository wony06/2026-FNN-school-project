"""Export a separate web view; keep original NEIS/HYU estimates immutable."""
import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from build_neis_reference import ALLERGENS
from allergy_policy_v2 import apply_reviewed_overlay, HELD_REFERENCE_CODES, USER_HELD_CODES, USER_REVIEW, MEAL_KEY_RENAMES

ROOT=Path(__file__).resolve().parent.parent
SOURCE=ROOT/'pipeline/hyu_allergy_estimates'


def load(p):return json.loads(p.read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def key(r):return (r['date'],r['shop'],r['category'],r['main'])


def suppress_partial_cutlet_shellfish(number,evidence,component):
    cutlet=bool(re.search(r'돈까스|돈가스',component['name'])) and not component['name'].endswith('소스')
    named=any(n['number']==18 for n in component['name_indications'])
    partial=0<evidence['labeled_record_count']<evidence['total_record_count']
    return number==18 and cutlet and partial and not named


def run(estimates_source=None, output_path=None, audit_path=None, verbose=True, source_provenance=None):
    source = Path(estimates_source) if estimates_source is not None else SOURCE
    output_path = Path(output_path) if output_path is not None else ROOT/'web/allergy-data.json'
    audit_path = Path(audit_path) if audit_path is not None else ROOT/'pipeline/hyu_allergy_filter_audit.json'
    protected=[ROOT/'web/site_data.json',ROOT/'web/menu_exchange_snapshot.json',
        ROOT/'web/personal-score.js',ROOT/'web/recommendation-view.js',ROOT/'web/instant-rice.js',
        ROOT/'pipeline/neis_reference/reference.sqlite3',source/'meal_estimates.json']
    hashes={str(p.relative_to(ROOT)):sha(p) for p in protected}
    estimates=load(source/'meal_estimates.json')
    rows=load(ROOT/'web/site_data.json')
    assert len({tuple(m['meal_key']) for m in estimates})==len(estimates)
    assert {MEAL_KEY_RENAMES.get(tuple(m['meal_key']),tuple(m['meal_key'])) for m in estimates}=={key(r) for r in rows}, 'Regenerate estimates for all current menus before exporting'
    ref=load(source/'reference_statistics.json')
    source_records=[json.loads(x) for x in (source/'source_records.jsonl').read_text(encoding='utf-8').splitlines()]
    estimates,ref,source_records,policy_audit=apply_reviewed_overlay(ROOT,estimates,ref,source_records)
    source_map={r['record_id']:{'school':r['school_name'],'schoolCode':r['school_code'],
        'date':r['meal_date'],'mealType':r['meal_type'],'sourceText':r['source_text'],
        'allergyNumbers':r['allergy_numbers'],'referenceMenu':r['normalized_menu_name']} for r in source_records}
    ref_ids={}
    for r in source_records:
        if r['label_status']=='표기':
            for n in r['allergy_numbers']:
                ref_ids.setdefault((r['normalized_menu_name'],n),[]).append(r['record_id'])
    references={name:{'recordCount':a['record_count'],'schoolCount':a['school_count'],
        'unlabeledCount':a['unlabeled_record_count'],'reviewCount':a['review_record_count'],
        'allergens':{str(s['number']):{'labeledRecords':s['labeled_record_count'],
            'labeledSchools':s['labeled_school_count'],'totalRecords':s['total_record_count'],
            'recordIds':sorted(set(ref_ids.get((name,s['number']),[])))} for s in a['allergens']}}
        for name,a in ref.items()}
    meals=[];corrections=[];review=[]
    for m in estimates:
        components={c['component_id']:c for c in m['components']}
        held=m['unknowns']['choice_or_separator_integration_withheld']
        allergens=[];suppressed=[]
        for a in m['allergens']:
            named=[{'component':e['component_name'],'terms':e['matched_terms'],
                'basis':e.get('basis'),'provenance':e.get('provenance')} for e in a['name_evidence']]
            active=[]
            for e in a['neis_evidence']:
                c=components[e['component_id']]
                partial=0<e['labeled_record_count']<e['total_record_count']
                evidence={'component':e['component_name'],'reference':e['reference_menu'],
                          **({'provenance':e['provenance']} if e.get('provenance') else {})}
                reviewed_hold=(e['reference_menu'],a['number']) in HELD_REFERENCE_CODES and not any(n['number']==a['number'] for n in c['name_indications'])
                if reviewed_hold or suppress_partial_cutlet_shellfish(a['number'],e,c):
                    entry={'code':a['number'],**evidence,'labeledRecords':e['labeled_record_count'],
                        'labeledSchools':e['labeled_school_count'],'totalRecords':e['total_record_count'],
                        'recordIds':e['source_record_ids'],'state':'미확인',
                        'reviewSource':('사용자 제공 정보; 공식 원재료 확인 아님' if (e['reference_menu'],a['number']) in USER_HELD_CODES else 'NEIS 근거 적합성 검토'),
                        'reviewedAt':USER_REVIEW['reviewedAt'],
                        'reason':('사용자 답변상 해당 재료 미사용. 외부 NEIS 근거는 자동 적용 보류·원재료 확인 필요.' if (e['reference_menu'],a['number']) in USER_HELD_CODES else '학교별 부재료·제품 배합 차이: 한양대 적용 근거 미확인. 자동 적용 보류·원재료 확인 필요.' if reviewed_hold else '돈까스류의 일부 NEIS 기록에만 조개류 표시. 메뉴명·확인 원재료 단서가 없어 자동 적용 제외.'),
                        'policy':'reviewed-reference-hold-v2' if reviewed_hold else 'partial-cutlet-shellfish-v1'}
                    suppressed.append(entry);corrections.append({'key':m['meal_key'],**entry})
                else:
                    active.append(evidence)
                    if a['number']==18 and partial:
                        review.append({'key':m['meal_key'],**evidence,'labeledRecords':e['labeled_record_count'],
                            'totalRecords':e['total_record_count'],'decision':'근거 보존; 추가 보정 규칙 미적용'})
            if named or active:
                allergens.append({'code':a['number'],'nameEvidence':named,'neisEvidence':active})
        assert not held or not allergens
        raw_key=m['meal_key']
        meals.append({'key':raw_key,'mealId':hashlib.sha256(json.dumps(raw_key,ensure_ascii=False,separators=(',',':')).encode()).hexdigest(),
            'state':'choice_withheld' if held else 'estimated_unverified','actualIngredientsConfirmed':False,
            'allergens':allergens,'suppressed':suppressed,
            'unknownComponents':m['unknowns']['components_without_reference_match'],
            'excludedCalculationCount':len(m['excluded_calculation_components']),
            'userReviewNotes':[{'component':c['name'],**c['userReviewNotes']} for c in m['components'] if c.get('userReviewNotes')]})
    published_hashes=dict(hashes)
    if source_provenance is not None:
        published_hashes.pop(str((source/'meal_estimates.json').relative_to(ROOT)),None)
        published_hashes.update(source_provenance)
    result={'schemaVersion':1,'policyVersion':'reviewed-reference-hold-v2',
        'generatedAt':datetime.now(timezone.utc).isoformat(),'sourceSha256':published_hashes,
        'allergens':[{'code':n,'name':name} for n,name in ALLERGENS.items()],
        'meals':meals,'references':references,'sourceRecords':source_map}
    counts={str(n):sum(any(a['code']==n for a in m['allergens']) for m in meals) for n in ALLERGENS}
    audit={'policyReview':policy_audit,'menuCount':len(meals),'excludedByAllergen':counts,'suppressedEvidenceCount':len(corrections),
        'correctedMealCount':len({tuple(e['key']) for e in corrections}),
        'choiceWithheldMenus':sum(m['state']=='choice_withheld' for m in meals),
        'excludedCalculationOccurrences':sum(m['excludedCalculationCount'] for m in meals),
        'corrections':corrections,'otherPartialShellfishEvidenceRetained':review,'protectedSha256':published_hashes}
    output_path.write_text(json.dumps(result,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    audit_path.write_text(json.dumps(audit,ensure_ascii=False,indent=2),encoding='utf-8')
    assert all(sha(p)==hashes[str(p.relative_to(ROOT))] for p in protected)
    if verbose:
        print(json.dumps({k:v for k,v in audit.items() if k not in ('corrections','otherPartialShellfishEvidenceRetained','protectedSha256','policyReview')},ensure_ascii=False,indent=2))
    return result, audit


if __name__=='__main__':
    import sys
    if hasattr(sys.stdout,'reconfigure'):sys.stdout.reconfigure(encoding='utf-8')
    from sync_allergy_data import sync_allergy_data
    sync_allergy_data()
