"""Refresh only posted lunch photos; never recompute menus, nutrition, or ranking."""
import argparse
import copy
import hashlib
import io
import json
import re
import shutil
import urllib.request
from datetime import date, timedelta
from pathlib import Path
from urllib.parse import urljoin
from lxml import html
from PIL import Image, ImageOps
from parse_month import parse_main_and_sides, is_lunch_cat

ROOT = Path(__file__).resolve().parent.parent
BASE = 'https://fnb.hanyang.ac.kr'
CATEGORIES = {'105': {'한식','양식','즉석'}, '204': {'정식','일품'}}
# 2026-11-15 user approval: attach only the posted photo; retain the old name/nutrients.
APPROVED_PHOTO_NAMES = {('2026-11-12','204','정식','닭볶음탕','순살닭볶음탕')}

def read(path): return json.loads(path.read_text(encoding='utf-8'))
def write(path,data): path.write_text(json.dumps(data,ensure_ascii=False,indent=1)+'\n',encoding='utf-8')
def fetch(url):
    req=urllib.request.Request(url,headers={'User-Agent':'Mozilla/5.0'})
    with urllib.request.urlopen(req,timeout=30) as response: return response.read()
def scrape(day):
    url=f'{BASE}/front/fnbmMdMenu?date={day}'
    doc=html.fromstring(fetch(url))
    result=[]
    for section in doc.xpath('//div[contains(concat(" ",normalize-space(@class)," ")," menu-slide-item ")]'):
        shop=section.xpath('string(.//div[contains(@class,"round")]/span)').strip()
        if shop not in ('105','401','204'): continue
        for li in section.xpath('.//ul[contains(@class,"menu-slide")]/li'):
            def text(cls): return li.xpath('string(.//*[contains(concat(" ",normalize-space(@class)," ")," '+cls+' ")])').strip()
            category=text('category'); name=text('title')
            if shop=='401':
                if not is_lunch_cat('s401', category): continue
            elif category not in CATEGORIES[shop]: continue
            if not name: continue
            styles=li.xpath('.//*[contains(@class,"thumb-img")]/@style')
            match=re.search(r'url\(["\']?([^"\')]+)',styles[0]) if styles else None
            result.append({'date':day,'shop':shop,'category':category,'name':name,
                'desc':text('desc'),'sourcePage':url,'imageUrl':urljoin(BASE,match.group(1)) if match else None})
    return result

def cached_rows(day,cache):
    result=[]
    for shop in ('105','401','204'):
        for item in cache.get(day,{}).get('s'+shop,{}).get('items',[]):
            result.append({'date':day,'shop':shop,'category':item['category'],'name':item['name'],
                'desc':item.get('desc',''),'sourcePage':f'{BASE}/front/fnbmMdMenu?date={day}',
                'imageUrl':item.get('img')})
    return result


def run(start,end,missing_only=False,source_file=None):
    days=[]; current=date.fromisoformat(start)
    while current<=date.fromisoformat(end):
        days.append(current.isoformat());current+=timedelta(days=1)
    source=read(ROOT/'hanyang_menu_month.json');original_source=copy.deepcopy(source)
    source_by_date={d['date']:d for d in source['days']}
    sites={path:read(ROOT/path) for path in ('site_data.json','web/site_data.json')}
    originals=copy.deepcopy(sites);mapping=read(ROOT/'photo_mapping.json')
    protected={str(f):hashlib.sha256(f.read_bytes()).hexdigest() for f in [ROOT/'web/allergy-data.json',ROOT/'web/menu_exchange_snapshot.json',ROOT/'month_lunch_trays.json']}
    report={'start':start,'end':end,'collected':[],'missing':[],'existing':[],'review':[],'sourceRows':[]}
    cache={d['date']:d for d in read(Path(source_file))['days']} if source_file else None
    for day in days:
        fetched=cached_rows(day,cache) if cache is not None else scrape(day)
        report['sourceRows'].extend(fetched)
        for item in fetched:
            skey='s'+item['shop']
            old=[r for r in source_by_date.get(day,{}).get(skey,{}).get('items',[]) if r['category']==item['category']]
            new_main=parse_main_and_sides(item['name'],item.get('desc',''))[0]
            matches=[r for r in old if r['name']==item['name']]
            if not matches:
                matches=[r for r in old if parse_main_and_sides(r['name'],r.get('desc',''))[0]==new_main
                         or (day,item['shop'],item['category'],parse_main_and_sides(r['name'],r.get('desc',''))[0],new_main) in APPROVED_PHOTO_NAMES]
            if len(matches)!=1:
                report['review'].append({'source':item,'reason':'기존 메뉴명으로 유일하게 연결할 수 없음'});continue
            previous=matches[0]
            old_main=parse_main_and_sides(previous['name'],previous.get('desc',''))[0]
            site_matches={path:[r for r in rows if r['date']==day and r['shop']==item['shop'] and r['category']==item['category']
                               and (r['main']==old_main or r.get('sourceMenuText')==previous['name'])] for path,rows in sites.items()}
            if not all(len(rows)==1 for rows in site_matches.values()):
                report['review'].append({'source':item,'reason':'웹 메뉴 식별자가 유일하지 않아 연결 보류'});continue
            if missing_only and all(rows[0].get('photo') and (ROOT/'web/menu_photos_web'/rows[0]['photo']).is_file() for rows in site_matches.values()):
                report['existing'].append(item);continue
            if previous['name']!=item['name']:
                report['review'].append({'date':day,'shop':item['shop'],'category':item['category'],
                    'previousName':previous['name'],'currentName':item['name'],'reason':'구성 메뉴 변경; 영양값·구성 메뉴 수정 안 함'})
            if not item['imageUrl']:
                report['missing'].append(item);continue
            key=f"{day}_{item['shop']}_{item['category']}"
            cat_idx=old.index(previous)
            if cat_idx:key+=f'#{cat_idx}'
            if key in mapping and (ROOT/'web/menu_photos_web'/mapping[key]).is_file() and previous.get('img')==item['imageUrl']:
                report['existing'].append(item);continue
            raw=fetch(item['imageUrl'])
            image=ImageOps.exif_transpose(Image.open(io.BytesIO(raw))).convert('RGB')
            if image.width>800:
                image=image.resize((800,round(image.height*800/image.width)),Image.Resampling.LANCZOS)
            filename=hashlib.sha256(item['imageUrl'].encode()).hexdigest()[:24]+'.jpg'
            target=ROOT/'menu_photos_web'/filename;target.parent.mkdir(exist_ok=True)
            image.save(target,'JPEG',quality=78)
            (ROOT/'web/menu_photos_web').mkdir(exist_ok=True)
            shutil.copy2(target,ROOT/'web/menu_photos_web'/filename)
            mapping[key]=filename;previous['img']=item['imageUrl']
            for matches in site_matches.values():matches[0]['photo']=filename
            report['collected'].append({**item,'localPhoto':filename,'sha256':hashlib.sha256(target.read_bytes()).hexdigest()})
    for path,rows in sites.items():
        assert len(rows)==len(originals[path])
        assert [{k:v for k,v in r.items() if k!='photo'} for r in rows]==[{k:v for k,v in r.items() if k!='photo'} for r in originals[path]]
    def without_images(value):
        if isinstance(value,list): return [without_images(v) for v in value]
        if isinstance(value,dict): return {k:without_images(v) for k,v in value.items() if k!='img'}
        return value
    assert without_images(source)==without_images(original_source)
    for path,rows in sites.items():write(ROOT/path,rows)
    write(ROOT/'hanyang_menu_month.json',source);write(ROOT/'photo_mapping.json',mapping)
    assert all(hashlib.sha256(Path(f).read_bytes()).hexdigest()==digest for f,digest in protected.items())
    report['preservedMenuCounts']={path:len(rows) for path,rows in sites.items()}
    write(ROOT/f'pipeline/photo_refresh_{end}.json',report)
    print(json.dumps({k:(len(v) if isinstance(v,list) else v) for k,v in report.items() if k!='sourceRows'},ensure_ascii=False))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--start',required=True);parser.add_argument('--end',required=True)
    parser.add_argument('--missing-only',action='store_true')
    parser.add_argument('--source-file',help='Previously fetched source JSON; avoids repeated requests')
    args=parser.parse_args();run(args.start,args.end,args.missing_only,args.source_file)
