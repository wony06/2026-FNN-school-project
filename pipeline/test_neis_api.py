"""Read NEIS_API_KEY from the environment; test one school's October 2026 meals.

Run: python pipeline/test_neis_api.py
No key, request URL, or HTTP exception containing a key is written to output.
"""
import argparse
import html
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

BASE = 'https://open.neis.go.kr/hub/'


def api_key():
    key = os.environ.get('NEIS_API_KEY', '').strip()
    if not key and sys.platform == 'win32':
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, 'Environment') as registry:
                key = winreg.QueryValueEx(registry, 'NEIS_API_KEY')[0].strip()
        except FileNotFoundError:
            pass
    if not key:
        raise ValueError('NEIS_API_KEY 환경변수를 먼저 설정해주세요. 인증키 값은 출력하지 않습니다.')
    return key


def request_rows(service, key, **filters):
    rows, page = [], 1
    while True:
        params = {'KEY': key, 'Type': 'json', 'pIndex': page, 'pSize': 100, **filters}
        url = BASE + service + '?' + urllib.parse.urlencode(params)
        try:
            with urllib.request.urlopen(url, timeout=30) as response:
                data = json.load(response)
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f'{service}: HTTP {exc.code}') from None
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            raise RuntimeError(f'{service}: 연결 또는 JSON 응답 오류') from None
        if 'RESULT' in data:
            code = data['RESULT'].get('CODE')
            if code == 'INFO-200':
                return rows
            raise RuntimeError(f'{service}: NEIS 응답 코드 {code}')
        blocks = data.get(service, [])
        heads = [head for block in blocks for head in block.get('head', [])]
        codes = [head['RESULT']['CODE'] for head in heads if 'RESULT' in head]
        if codes != ['INFO-000']:
            raise RuntimeError(f'{service}: 정상 응답 코드 확인 실패')
        batch = [row for block in blocks for row in block.get('row', [])]
        total = next((head['list_total_count'] for head in heads if 'list_total_count' in head), 0)
        rows.extend(batch)
        if len(rows) >= total:
            return rows
        if not batch:
            raise RuntimeError(f'{service}: 페이지 데이터 누락')
        page += 1


def parse_dishes(raw):
    result = []
    for line in re.split(r'<br\s*/?>|[\r\n]+', raw, flags=re.I):
        line = html.unescape(line).strip()
        if not line:
            continue
        markers = list(re.finditer(r'\(\s*(\d+(?:\s*\.\s*\d+)*\.?)[\s]*\)', line))
        numbers = sorted({int(n) for match in markers for n in re.findall(r'\d+', match.group(1))})
        if any(n < 1 or n > 19 for n in numbers):
            raise ValueError('알레르기 번호 범위 확인 필요')
        name = re.sub(r'\(\s*\d+(?:\s*\.\s*\d+)*\.?\s*\)', '', line).strip()
        result.append({'name': name, 'allergyNumbers': numbers, 'sourceText': line,
                       'allergyLabelPresent': bool(markers)})
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--school', default='한양대학교사범대학부속고등학교')
    args = parser.parse_args()
    key = api_key()
    schools = request_rows('schoolInfo', key, SCHUL_NM=args.school)
    exact = [school for school in schools if school['SCHUL_NM'] == args.school]
    if len(exact) != 1:
        raise ValueError(f'학교명 정확 일치 {len(exact)}개: 학교 선택 확인이 필요합니다.')
    school = exact[0]
    meals = request_rows('mealServiceDietInfo', key,
        ATPT_OFCDC_SC_CODE=school['ATPT_OFCDC_SC_CODE'], SD_SCHUL_CODE=school['SD_SCHUL_CODE'],
        MLSV_FROM_YMD='20261001', MLSV_TO_YMD='20261031')
    meals.sort(key=lambda row: (row['MLSV_YMD'], row['MMEAL_SC_CODE']))
    dishes = []
    for meal in meals:
        for dish in parse_dishes(meal['DDISH_NM']):
            dishes.append({'date': meal['MLSV_YMD'], 'mealType': meal['MMEAL_SC_NM'], **dish})
    output = {'school': {field: school[field] for field in
        ('SCHUL_NM', 'ATPT_OFCDC_SC_CODE', 'SD_SCHUL_CODE')}, 'month': '2026-10',
        'mealCount': len(meals), 'dishCount': len(dishes), 'meals': meals, 'dishes': dishes,
        'notice': '빈 번호 목록은 원문에 알레르기 번호가 미표기되었다는 뜻이며 알레르기 안전을 의미하지 않습니다.'}
    # Fixed private diagnostic path already covered by .gitignore.
    path = Path(__file__).with_name('_debug_neis_october_2026.json')
    path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({**{k: output[k] for k in ('school', 'month', 'mealCount', 'dishCount')},
                      'examples': dishes[:5], 'output': str(path)}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    try:
        main()
    except (ValueError, RuntimeError) as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
