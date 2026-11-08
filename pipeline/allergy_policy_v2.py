"""Reviewed web-only allergy policy. Original estimates and NEIS database stay immutable."""
from copy import deepcopy
import json
import sqlite3
from pathlib import Path
from build_neis_reference import ALLERGENS, normalize_name
from match_hyu_neis import name_evidence

ALIASES = {
    '부대찌개*라면사리': '부대찌개&라면사리',
    '설렁탕*소면사리': '설렁탕&소면사리',
    '떡만두국': '떡만두국#',
    '소시지오므라이스': '소세지오므라이스',
}
# Initial reviewed pairs; user-reported holds below are additive. Cabbage-kimchi/shellfish stays active.
HELD_REFERENCE_CODES = {
    ('마카로니샐러드', 4), ('마카로니샐러드', 16), ('마카로니샐러드', 17),
    ('식혜', 11), ('무말랭이무침', 2),
}
USER_REVIEW = json.loads((Path(__file__).with_name('allergy_user_reviews.json')).read_text(encoding='utf-8'))
USER_HELD_CODES = {tuple(pair) for pair in USER_REVIEW['holdReferenceCodes']}
HELD_REFERENCE_CODES |= USER_HELD_CODES

# Exact historical key migration from latest main; do not infer new recipe ingredients.
MEAL_KEY_RENAMES = {
 ('2026-10-28','401','중식 - Korean Dining','치킨너겟버펄로볼 나초파이 양송이스프/맥앤치즈 브라운브레드&버터,잼 오이피클&할라피뇨 콜라 샐러드&토핑&드레싱'):
 ('2026-10-28','401','중식 - Korean Dining','치킨너겟버펄로볼'),
}

EXTRA_CUES = {1: ('에그',), 10: ('부타동', '포크'), 16: ('비프', '소불고기', '소머리')}

def revised_name_evidence(name):
    # Goulash is not oyster; imitation crab/rolled dumpling guards remain in original function.
    safe = name.replace('굴라쉬', '구라쉬').replace('굴라시', '구라시')
    evidence = {e['number']: e for e in name_evidence(safe)}
    normalized = normalize_name(name)
    for number, terms in EXTRA_CUES.items():
        found = [t for t in terms if t in normalized]
        if found:
            entry = evidence.setdefault(number, {'number': number, 'name': ALLERGENS[number],
                'matched_terms': [], 'basis': '메뉴명 명시·번역 단서; 실제 원재료/제품 확인 아님'})
            entry['matched_terms'] = sorted(set(entry['matched_terms'] + found))
    if name in USER_REVIEW['porkComponentNames']:
        entry = evidence.setdefault(10, {'number': 10, 'name': ALLERGENS[10], 'matched_terms': []})
        entry['matched_terms'] = sorted(set(entry['matched_terms'] + [name]))
        entry['basis'] = '사용자 제공 원재료 단서: 돼지고기 사용. 공식 레시피·제품 라벨 미확인'
        entry['provenance'] = {'type': 'user_report', 'reviewedAt': USER_REVIEW['reviewedAt'],
            'actualIngredientsVerified': False}
    for number in USER_REVIEW.get('userReportedAllergenCodes', {}).get(name, []):
        entry = evidence.setdefault(number, {'number': number, 'name': ALLERGENS[number], 'matched_terms': []})
        entry['matched_terms'] = sorted(set(entry['matched_terms'] + [name]))
        entry['basis'] = '사용자 제공 원재료 단서: ' + ALLERGENS[number] + ' 사용. 공식 레시피·제품 라벨 미확인'
        entry['provenance'] = {'type': 'user_report', 'reviewedAt': USER_REVIEW['reviewedAt'], 'actualIngredientsVerified': False}
    return [evidence[n] for n in sorted(evidence)]

def apply_reviewed_overlay(root, originals, refs, source_records):
    meals = deepcopy(originals)
    refs = deepcopy(refs)
    records = {r['record_id']: r for r in source_records}
    db = sqlite3.connect((root/'pipeline/neis_reference/reference.sqlite3').as_uri()+'?mode=ro', uri=True)
    alias_refs = set(ALIASES.values())
    for target in alias_refs:
        row = db.execute('SELECT metadata_json FROM menu_aggregates WHERE normalized_menu_name=?', (target,)).fetchone()
        assert row, target
        refs[target] = json.loads(row[0])
    for (raw,) in db.execute('SELECT source_json FROM records'):
        record = json.loads(raw)
        if record['normalized_menu_name'] in alias_refs:
            records[record['record_id']] = record
    db.close()
    alias_matches = []
    name_changes = []
    for meal in meals:
        original_key = tuple(meal['meal_key'])
        if original_key in MEAL_KEY_RENAMES:
            meal['meal_key'] = list(MEAL_KEY_RENAMES[original_key])
            meal['originalMealKey'] = list(original_key)
        held = meal['unknowns']['choice_or_separator_integration_withheld']
        for component in meal['components']:
            user_notes = next((r for r in USER_REVIEW.get('batch2', [])+USER_REVIEW.get('batch3', []) if r['subject']==component['name']), None)
            if user_notes:
                component['userReviewNotes'] = deepcopy(user_notes)
                component['userReviewNotes']['evidenceType'] = 'user_report_recipe_unverified'
            old = component['name_indications']
            component['name_indications'] = revised_name_evidence(component['name'])
            if old != component['name_indications']:
                name_changes.append({'key': meal['meal_key'], 'component': component['name'],
                    'before': old, 'after': component['name_indications']})
            target = ALIASES.get(component['name'])
            if target:
                component['match_type'] = 'synonym'
                component['reference_menu'] = target
                component['unresolved']['no_confirmed_reference_match'] = False
                component['neis_possible'] = []
                for stat in refs[target]['allergens']:
                    if not stat['labeled_record_count']: continue
                    ids = sorted(r['record_id'] for r in records.values()
                        if r['normalized_menu_name']==target and r['label_status']=='표기'
                        and stat['number'] in r['allergy_numbers'])
                    assert len(ids)==stat['labeled_record_count']
                    component['neis_possible'].append({**stat, 'reference_menu': target,
                        'source_record_ids': ids, 'meaning': '표기 동의어의 NEIS 포함 가능 근거; 실제 한양대 배합 미확인'})
                alias_matches.append({'key': meal['meal_key'], 'component': component['name'],
                    'reference': target, 'integrationApplied': not held})
        for allergen in meal['allergens']:
            n = allergen['number']
            allergen['name_evidence'] = []
            allergen['neis_evidence'] = []
            for c in meal['components']:
                if held or not c['integration_applied']: continue
                base = {'component_id': c['component_id'], 'component_name': c['name']}
                allergen['name_evidence'].extend({**base, **e} for e in c['name_indications'] if e['number']==n)
                allergen['neis_evidence'].extend({**base, **e} for e in c['neis_possible'] if e['number']==n)
            named, neis = allergen['name_evidence'], allergen['neis_evidence']
            allergen['classification'] = ('name_and_neis_possible' if named and neis else
                'name_indicated' if named else 'neis_possible' if neis else 'unknown')
            ids = sorted({rid for e in neis for rid in e['source_record_ids']})
            allergen['supporting_source_record_ids'] = ids
            allergen['distinct_supporting_record_count'] = len(ids)
            allergen['distinct_supporting_school_count'] = len({records[rid]['school_code'] for rid in ids})
        meal['unknowns']['components_without_reference_match'] = [c['name'] for c in meal['components']
            if c['unresolved']['no_confirmed_reference_match']]
    return meals, refs, list(records.values()), {'aliasMatches': alias_matches, 'nameChanges': name_changes, 'userReview': USER_REVIEW, 'mealKeyRenames':[{'before':list(k),'after':list(v)} for k,v in MEAL_KEY_RENAMES.items()]}
