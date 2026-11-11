"""Incrementally connect source-supported menus to the reviewed allergy policy.

Called by both menu import and site-data export. Original 449-meal analysis and
NEIS database are read-only; later results and provenance live separately.
"""
import hashlib
import json
import os
import tempfile
from pathlib import Path

from allergy_policy_v2 import MEAL_KEY_RENAMES
from match_hyu_neis import run as match_menus
from classify_hyu_allergens import run as classify_menus
from export_allergy_web import run as export_web

ROOT = Path(__file__).resolve().parent.parent
BASE = ROOT / 'pipeline/hyu_allergy_estimates'
CACHE = ROOT / 'pipeline/hyu_allergy_incremental'


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                    separators=(',', ':')).encode()).hexdigest()


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def key(row):
    return tuple(row[n] for n in ('date', 'shop', 'category', 'main'))


def estimate_key(row):
    original = tuple(row['meal_key'])
    return MEAL_KEY_RENAMES.get(original, original)


def token(k):
    return json.dumps(k, ensure_ascii=False, separators=(',', ':'))


def source_fingerprints(rows, parsed, source):
    """Images, calories and calculated components must never become allergy evidence."""
    raw = {}
    for day in source['days']:
        for shop in ('105', '401', '204'):
            for item in day.get('s' + shop, {}).get('items', []):
                raw.setdefault((day['date'], shop, item['category']), []).append(
                    {n: item.get(n) for n in ('name', 'desc')})
    groups = {}
    for p in parsed:
        groups.setdefault((p['date'], p['shop'], p['category']), []).append(
            {n: p.get(n) for n in ('main', 'sides', 'cat_idx')})
    return {token(key(r)): digest({'key': key(r), 'sourceMenuText': r.get('sourceMenuText'),
                                  'parsed': groups.get(key(r)[:3], []),
                                  'raw': raw.get(key(r)[:3], [])}) for r in rows}


def validate_coverage(rows, exported):
    current = [key(r) for r in rows]
    actual = [tuple(m['key']) for m in exported['meals']]
    if len(set(current)) != len(current) or len(set(actual)) != len(actual):
        raise ValueError('알레르기 식단 식별자가 중복됩니다. 자동 연결을 중단합니다.')
    if set(current) != set(actual):
        raise ValueError('현재 메뉴와 알레르기 데이터가 1:1로 연결되지 않았습니다.')
    for meal in exported['meals']:
        assert not meal['actualIngredientsConfirmed']
        assert all(1 <= a['code'] <= 19 for a in meal['allergens'])
        assert meal['state'] != 'choice_withheld' or not meal['allergens']


def atomic_bytes(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, suffix='.tmp', delete=False) as f:
        temp = Path(f.name)
        f.write(content)
    try:
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + '\n').encode()


def write(path, value):
    atomic_bytes(path, json_bytes(value))


def sync_allergy_data(verbose=True):
    rows = read(ROOT / 'web/site_data.json')
    fingerprints = source_fingerprints(rows, read(ROOT / 'pipeline/month_lunch_parsed.json'),
                                      read(ROOT / 'hanyang_menu_month.json'))
    original = read(BASE / 'meal_estimates.json')
    historical = {estimate_key(m): m for m in original}
    registry_path = CACHE / 'registry.json'
    registry = read(registry_path) if registry_path.exists() else {}
    additions_path = CACHE / 'meal_estimates.json'
    additions = read(additions_path) if additions_path.exists() else []
    cached = {estimate_key(m): m for m in additions}
    dependency_paths = [BASE / n for n in ('meal_estimates.json', 'reference_statistics.json', 'source_records.jsonl')]
    dependency_paths += [ROOT / 'pipeline' / n for n in (
        'sync_allergy_data.py', 'match_hyu_neis.py', 'classify_hyu_allergens.py',
        'export_allergy_web.py', 'allergy_policy_v2.py', 'allergy_user_reviews.json', 'build_neis_reference.py')]
    dependency_paths.append(ROOT / 'pipeline/neis_reference/reference.sqlite3')
    # Missing reference files are errors; never silently report a successful refresh.
    policy_hash = digest({p.relative_to(ROOT).as_posix(): sha(p) for p in dependency_paths})
    policy_changed = registry.get('policyHash') != policy_hash
    stale = [r for r in rows if key(r) not in historical and key(r) not in cached
             or key(r) in cached and (policy_changed or registry.get('sourceFingerprints', {}).get(token(key(r))) != fingerprints[token(key(r))])
             or key(r) in historical and registry.get('sourceFingerprints', {}).get(token(key(r))) not in (None, fingerprints[token(key(r))])]
    web_path = ROOT / 'web/allergy-data.json'
    if (not stale and not policy_changed and registry.get('sourceFingerprints') == fingerprints
            and web_path.exists() and registry.get('webSha256') == sha(web_path)
            and registry.get('sourceSiteSha256') == sha(ROOT / 'web/site_data.json')):
        validate_coverage(rows, read(web_path))
        if verbose:
            print(f'알레르기 자동 연결 확인: {len(rows)}개, 미연결 0개 (변경 없음)')
        return {'menuCount': len(rows), 'analyzedMenus': 0, 'unlinkedMenus': 0, 'changed': False}

    CACHE.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='_build-', dir=CACHE) as temporary:
        stage = Path(temporary)
        refs = read(BASE / 'reference_statistics.json')
        records = {r['record_id']: r for r in map(json.loads, (BASE / 'source_records.jsonl').read_text(encoding='utf-8').splitlines())}
        if (CACHE / 'reference_statistics.json').exists():
            refs.update(read(CACHE / 'reference_statistics.json'))
            records.update({r['record_id']: r for r in map(json.loads, (CACHE / 'source_records.jsonl').read_text(encoding='utf-8').splitlines())})
        if stale:
            if verbose: print(f'알레르기 신규·변경 식단 {len(stale)}개 분석 중...', flush=True)
            match_menus(meals=stale, out_dir=stage / 'matching', verbose=False)
            classify_menus(input_dir=stage / 'matching', out_dir=stage / 'analysis', verbose=False)
            cached.update({estimate_key(m): m for m in read(stage / 'analysis/meal_estimates.json')})
            refs.update(read(stage / 'analysis/reference_statistics.json'))
            records.update({r['record_id']: r for r in map(json.loads, (stage / 'analysis/source_records.jsonl').read_text(encoding='utf-8').splitlines())})
        all_estimates = {**historical, **cached}
        combined = [all_estimates[key(r)] for r in rows]
        write(stage / 'meal_estimates.json', combined)
        write(stage / 'reference_statistics.json', refs)
        source_bytes = ''.join(json.dumps(r, ensure_ascii=False) + '\n' for r in records.values()).encode()
        atomic_bytes(stage / 'source_records.jsonl', source_bytes)
        source_provenance = {str((BASE/'meal_estimates.json').relative_to(ROOT)): sha(BASE/'meal_estimates.json'),
                             str(additions_path.relative_to(ROOT)): hashlib.sha256(json_bytes(list(cached.values()))).hexdigest(),
                             str((CACHE/'reference_statistics.json').relative_to(ROOT)): hashlib.sha256(json_bytes(refs)).hexdigest(),
                             str((CACHE/'source_records.jsonl').relative_to(ROOT)): hashlib.sha256(source_bytes).hexdigest()}
        result, audit = export_web(estimates_source=stage, output_path=stage / 'allergy-data.json',
                                   audit_path=stage / 'audit.json', verbose=False, source_provenance=source_provenance)
        validate_coverage(rows, result)
        # Publish only fully validated output. Preserve the original analysis and review rules.
        write(additions_path, list(cached.values()))
        write(CACHE / 'reference_statistics.json', refs)
        atomic_bytes(CACHE / 'source_records.jsonl', source_bytes)
        if stale:
            for directory in ('matching', 'analysis'):
                for p in (stage / directory).iterdir():
                    atomic_bytes(CACHE / 'last_batch' / directory / p.name, p.read_bytes())
        if verbose: print('알레르기 웹 데이터 연결 중...', flush=True)
        atomic_bytes(web_path, (stage / 'allergy-data.json').read_bytes())
        atomic_bytes(CACHE / 'filter_audit.json', (stage / 'audit.json').read_bytes())
        report = {'menuCount': len(rows), 'analyzedMenus': len(stale), 'unlinkedMenus': 0,
                  'historicalMenus': sum(key(r) in historical and key(r) not in cached for r in rows),
                  'incrementalMenus': sum(key(r) in cached for r in rows),
                  'choiceWithheldMenus': audit['choiceWithheldMenus'],
                  'excludedByAllergen': audit['excludedByAllergen'], 'changed': True}
        write(CACHE / 'summary.json', report)
        write(registry_path, {'schemaVersion': 1, 'policyHash': policy_hash,
                             'sourceFingerprints': fingerprints, 'webSha256': sha(web_path),
                             'sourceSiteSha256': sha(ROOT / 'web/site_data.json')})
    if verbose:
        print(json.dumps(report, ensure_ascii=False))
    return report


if __name__ == '__main__':
    sync_allergy_data()
