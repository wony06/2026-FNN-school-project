# -*- coding: utf-8 -*-
"""RCP_PARTS_DTLS 텍스트 -> [{name, amount_g}] 파서.
지원 포맷:
  "새송이버섯 100g(3개)"       -> name=새송이버섯, amount=100
  "닭고기살(100g)"             -> name=닭고기살,   amount=100
  "닭고기(가슴살, 30g)"         -> name=닭고기,     amount=30   (괄호 안 쉼표 보호)
  "시금치(포항초) 30"           -> name=시금치,     amount=30 (단위 생략시 g로 가정)
  "물 15ml"                    -> name=물,        amount=15 (ml는 g으로 근사)
  "통깨 약간" / "소금 적당량"    -> 수량 불명 -> 제외
  "달걀(1개)" / "양송이버섯(3개)" -> 중량(g) 없이 개수만 있음 -> excluded_no_weight로 별도 보고(합산에서 제외)
"""
import re

BULLET_RE = re.compile(r'^[●·\-]\s*')
BRACKET_TAG_RE = re.compile(r'^[\[［【][^\]］】]*[\]］】]\s*')
TRAILING_PAREN_RE = re.compile(r'[\(（][^\)）]*[\)）]\s*$')
LEADING_PAREN_AMOUNT_RE = re.compile(r'^(?P<name>[^\d\(（]+?)\s*[\(（]\s*(?:[^,()]*,\s*)?(?P<amt>\d+\.?\d*)\s*(?P<unit>g|ml)\s*[\)）]\s*$')
NAME_AMT_UNIT_RE = re.compile(r'^(?P<name>[^\d]+?)\s*(?P<amt>\d+\.?\d*)\s*(?P<unit>g|ml)\b')
BARE_NUMBER_END_RE = re.compile(r'^(?P<name>[^\d]+?)\s*(?P<amt>\d+\.?\d*)\s*$')
COUNT_ONLY_RE = re.compile(r'^(?P<name>[^\d\(（]+?)\s*[\(（]?\s*(?P<cnt>\d+\.?\d*)\s*(?P<cu>개|알|장|마리|모|조각|쪽|줄기|큰술|작은술|컵)\s*[\)）]?\s*$')
VAGUE_QTY = ("약간", "적당량", "적당히", "소량")


def _split_protecting_parens(line, sep=','):
    """괄호 안의 구분자는 무시하고 바깥쪽에서만 분리한다."""
    parts, depth, buf = [], 0, []
    for ch in line:
        if ch in '([（':
            depth += 1
            buf.append(ch)
        elif ch in ')]）':
            depth = max(0, depth - 1)
            buf.append(ch)
        elif ch == sep and depth == 0:
            parts.append(''.join(buf))
            buf = []
        else:
            buf.append(ch)
    if buf:
        parts.append(''.join(buf))
    return parts


def _strip_line_prefix(line):
    line = BULLET_RE.sub('', line.strip())
    line = BRACKET_TAG_RE.sub('', line)
    if ':' in line or '：' in line:
        head = re.split('[:：]', line, maxsplit=1)[0]
        if not re.search(r'\d', head) and len(head) <= 12:
            line = re.split('[:：]', line, maxsplit=1)[1].strip()
    return line.strip()


def _clean_name(name):
    name = name.strip().strip(',').strip()
    name = TRAILING_PAREN_RE.sub('', name).strip()
    name = re.sub(r'^\[.*?\]', '', name).strip()
    return name


def parse_ingredients(text):
    """RCP_PARTS_DTLS 원문 파싱.
    반환: {"items": [{"name","amount_g","unit","raw"}, ...],
           "excluded_no_weight": [{"name","raw"}, ...]}   # 개수만 있고 g/ml 중량 불명이라 합산에서 뺀 것들
           "excluded_vague": [raw, ...]}                  # "약간"/"적당량" 등 수량 자체가 불명확한 것들
    """
    result = {"items": [], "excluded_no_weight": [], "excluded_vague": []}
    if not text:
        return result
    text = text.replace('\r', '')

    tokens = []
    for line in text.split('\n'):
        line = line.strip()
        if not line:
            continue
        line = _strip_line_prefix(line)
        if not line:
            continue
        for part in _split_protecting_parens(line, ','):
            part = part.strip()
            if part:
                tokens.append(part)

    for tok in tokens:
        if any(v in tok for v in VAGUE_QTY):
            result["excluded_vague"].append(tok)
            continue

        m = LEADING_PAREN_AMOUNT_RE.match(tok)
        if m:
            name = _clean_name(m.group('name'))
            if name:
                result["items"].append({"name": name, "amount_g": float(m.group('amt')), "unit": m.group('unit'), "raw": tok})
            continue

        m = NAME_AMT_UNIT_RE.match(tok)
        if m:
            name = _clean_name(m.group('name'))
            if name:
                result["items"].append({"name": name, "amount_g": float(m.group('amt')), "unit": m.group('unit'), "raw": tok})
            continue

        m = BARE_NUMBER_END_RE.match(tok)
        if m:
            name = _clean_name(m.group('name'))
            if name:
                result["items"].append({"name": name, "amount_g": float(m.group('amt')), "unit": "g(가정)", "raw": tok})
            continue

        m = COUNT_ONLY_RE.match(tok)
        if m:
            name = _clean_name(m.group('name'))
            result["excluded_no_weight"].append({"name": name or tok, "raw": tok, "count": m.group('cnt'), "count_unit": m.group('cu')})
            continue

        # 위 어떤 패턴에도 안 걸리면(파싱 실패) 원문 그대로 미상 처리
        result["excluded_no_weight"].append({"name": tok, "raw": tok, "count": None, "count_unit": None})

    return result


if __name__ == "__main__":
    import json, random, os
    with open(r"C:\Users\ST-USER\Desktop\2026 학술제\recipe_db_full.json", encoding="utf-8") as f:
        recipes = json.load(f)
    random.seed(1)
    sample = random.sample(recipes, 15)
    out = []
    for r in sample:
        out.append(f'--- {r["name"]} (way={r["way"]}) ---')
        out.append(f'RAW: {r["ingredients"]!r}')
        parsed = parse_ingredients(r["ingredients"])
        for p in parsed["items"]:
            out.append(f'  OK   {p["name"]} = {p["amount_g"]}{p["unit"]}   <- {p["raw"]!r}')
        for p in parsed["excluded_no_weight"]:
            out.append(f'  개수형(중량불명) {p["name"]}   <- {p["raw"]!r}')
        for raw in parsed["excluded_vague"]:
            out.append(f'  불명확수량       <- {raw!r}')
        total = sum(p["amount_g"] for p in parsed["items"])
        out.append(f'  TOTAL parsed weight: {total}g (recipe_db weight field: {r["weight"]})')
    with open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "_debug_parser_test.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(out))
    print("done")
