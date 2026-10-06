"""Restore source menu titles while preserving calculation identities and values."""
import copy
import hashlib
import json
import re
from pathlib import Path
from parse_month import parse_main_and_sides, parse_month_lunches

ROOT = Path(__file__).resolve().parent.parent
LABELS = {
    '스파게티_간편조리세트_해장파스타': '해장파스타',
    '미소된장국_100g분석자료': '미소된장국',
    '라멘_소유라멘': '쇼유라멘',
    '황태구이_양념': '황태무침',
    '된장국_두부': '된장국',
    '닭볶음(닭갈비)_매운양념': '불닭볶음',
    '삶은파스타면_펜네대체': '펜네파스타',
    '옥수수통조림_레시피': '옥수수',
    '파르메산치즈_레시피': '파르메산치즈',
    '건조파슬리_레시피': '파슬리',
    '차돌박이_원재료': '차돌박이',
    '해장국_우거지': '우거지해장국',
    '데친고사리_레시피': '고사리',
    '주먹밥_참치': '참치주먹밥',
    **{'아쿠아_'+n:n for n in ['어린잎','방울토마토','새싹','물','식초','매실청','레몬즙','유자청']},
}

def load(path):
    return json.loads(path.read_text(encoding='utf-8'))

def key(row):
    return (row['date'],row['shop'],row['category'],row['main'])

def clean_source(source):
    # Remove notices as complete phrases before tokenization (e.g. [SOLD OUT]).
    source=re.sub(r'\[[^\]]*\]|<[^>]*>|\*\*[^*]*\*\*', '', source).strip()
    return re.sub(r'^\(품절\)\s*', '', source)

def source_title(row, parsed):
    source=row.get('sourceMenuText')
    if source:
        source=clean_source(source)
        if source.startswith(('뻐없는 감자탕','뼈없는 감자탕')):
            return ' '.join(source.split()[:2])
        if source.startswith('김신영의 열쫄냉'):
            return '김신영의 열쫄냉'
        if source.startswith('초복 삼계탕'):
            return '삼계탕'
        if source.startswith('포크슈니첼 &미니굴라쉬'):
            return '포크슈니첼 &미니굴라쉬'
        return parse_main_and_sides(source, 'side dishes' if row['shop']=='105' else '-')[0]
    candidates=[r for r in parsed if (r['date'],r['shop'],r['category']) == (row['date'],row['shop'],row['category'])]
    if any(r['main']==row['main'] for r in candidates):
        return row['main']
    if len(candidates)==1:
        return candidates[0]['main']
    return row['main']

def rewrite_labels(row):
    if 'components' in row:
        changed=[LABELS.get(n,n) for n in row['components']]
        if changed != row['components']:
            row.setdefault('calculationComponents',row['components'])
            row['components']=changed
    for name in ('itemDetails','item_detail'):
        for item in row.get(name,[]):
            if item.get('display') in LABELS:
                item.setdefault('calculationName',item['display'])
                item['display']=LABELS[item['display']]
    if '구성요소_목록' in row:
        row.setdefault('계산용_구성요소_목록',row['구성요소_목록'])
        row['구성요소_목록']=[LABELS.get(n,n) for n in row['구성요소_목록']]

def run():
    web_path=ROOT/'web/site_data.json'
    rows=load(web_path)
    before=copy.deepcopy(rows)
    parsed=parse_month_lunches()
    renamed={}
    for row in rows:
        title=source_title(row,parsed)
        if title!=row['main']:
            renamed[key(row)]=title
            row.setdefault('calculationMain',row['main'])
            row['main']=title
        rewrite_labels(row)
    # Only labels/traceability fields may change; nutritional and exchange values stay identical.
    for old,new in zip(before,rows):
        allowed={'main','components','itemDetails','calculationMain','calculationComponents'}
        assert {k:v for k,v in old.items() if k not in allowed} == {k:v for k,v in new.items() if k not in allowed}
        for a,b in zip(old.get('itemDetails',[]),new.get('itemDetails',[])):
            assert {k:v for k,v in a.items() if k!='display'} == {k:v for k,v in b.items() if k not in ('display','calculationName')}
    web_path.write_text(json.dumps(rows,ensure_ascii=False),encoding='utf-8')
    for filename in ('site_data.json','month_lunch_trays.json','pipeline/month_lunch_parsed.json'):
        p=ROOT/filename
        data=load(p)
        for row in data:
            oldkey=key(row)
            if oldkey in renamed:
                row.setdefault('calculationMain',row['main'])
                row['main']=renamed[oldkey]
            rewrite_labels(row)
        p.write_text(json.dumps(data,ensure_ascii=False,indent=1),encoding='utf-8')
    snapshot_path=ROOT/'web/menu_exchange_snapshot.json'
    snapshot=load(snapshot_path)
    for entry in snapshot['entries']:
        k=tuple(entry['key'])
        if k in renamed:
            entry.setdefault('calculationMain',entry['key'][3])
            entry['key'][3]=renamed[k]
            entry['sourceMain']=renamed[k]
    assert len({tuple(e['key']) for e in snapshot['entries']})==len(snapshot['entries'])
    snapshot['sourceSha256']=hashlib.sha256(web_path.read_bytes()).hexdigest()
    snapshot_path.write_text(json.dumps(snapshot,ensure_ascii=False,indent=1),encoding='utf-8')
    # Keep frozen reference scores intact; restore titles in descriptive membership only.
    ref_path=ROOT/'web/nrf_reference_fixed.json'
    ref=load(ref_path)
    original_scores=ref['scores'][:]
    def restore_member(obj):
        if isinstance(obj,dict):
            if all(k in obj for k in ('date','shop','category','main')) and key(obj) in renamed:
                obj['main']=renamed[key(obj)]
            for v in obj.values():restore_member(v)
        elif isinstance(obj,list):
            if len(obj)>=4 and all(isinstance(v,str) for v in obj[:4]) and tuple(obj[:4]) in renamed:
                obj[3]=renamed[tuple(obj[:4])]
            for v in obj:restore_member(v)
    restore_member(ref.get('members',[]))
    assert ref['scores']==original_scores
    ref_path.write_text(json.dumps(ref,ensure_ascii=False,indent=1),encoding='utf-8')
    output=ROOT.parents[2]/'outputs'
    report=[{'date':k[0],'shop':k[1],'category':k[2],'previous':k[3],'original':v} for k,v in renamed.items()]
    (output/'restored-menu-names.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'restoredTitles':len(renamed),'restoredComponentMenus':sum(a['components']!=b['components'] for a,b in zip(before,rows)), 'changes':report},ensure_ascii=False))

if __name__=='__main__':run()
