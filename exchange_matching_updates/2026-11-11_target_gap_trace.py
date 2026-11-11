import json, sys, math, io
sys.path.insert(0, 'pipeline')
import exchange_unit as X
import build_month as bm

LOG=[]
_orig=X._add_ingredient
def patched(units, raw_group_name, rec, w):
    before=dict(units)
    ok=_orig(units, raw_group_name, rec, w)
    if ok:
        g=[k for k in units if abs(units[k]-before[k])>1e-12]
        for k in g:
            LOG.append((rec.get('식품명'), raw_group_name, round(w,1), k, round(units[k]-before[k],3)))
    else:
        LOG.append((rec.get('식품명') if rec else None, raw_group_name, round(w,1), 'SKIP', 0))
    return ok
X._add_ingredient=patched

trays=json.load(open('month_lunch_trays.json',encoding='utf-8'))
flag_mains=set(l.strip() for l in open(sys.argv[1],encoding="utf-8") if l.strip())
GR=X.EXCHANGE_GROUPS
SK1=("돈까스소스","브라운소스","쌈장","양파간장","타르타르소스","스위트칠리","타르소스","칠리소스","머스타드","카레소스","겨자소스","동그랑땡소스","레몬홍차","복숭아티","칠리S","스리라차소스")
SK2=("우동국","우동국물","미소국","미소장국","케찹","케첩","간장","초간장","초장")
out=[]
for t in trays:
    if t['date']<'2026-10-26': continue
    key=f"{t['date']} {t['shop']} {t['main']}"
    if key not in flag_mains: continue
    main=t.get('calculationMain',t['main']); shop=t['shop']; date=t['date']
    out.append(f"\n######## {key} [{t['category']}] kcal={t['kcal']} 저장값={ {k:t['식품교환단위'][k] for k in GR} }")
    tot={g:0.0 for g in GR}
    for it in t['item_detail']:
        d=it['display']
        if it.get('exchange_excluded_reason'): out.append(f"  - {d}: EXCLUDED({it['exchange_excluded_reason'][:60]})"); continue
        if d=='야구르트' or d in SK1 or d in SK2: out.append(f"  - {d}: skip(조미료/음료)"); continue
        if shop=='401' and d=='김치2종' and date in X.KIMCHI_PAIR_EXCLUDED_DATES: out.append(f"  - {d}: unmatched(사진없음)"); continue
        ew=(9.0 if '마요덮밥' in main else 12.0) if shop=='105' and d=='마요네즈' else it.get('exchange_weight_g', it['weight_g'])
        LOG.clear()
        r=None
        if shop=='401' and d=='김치2종': r=X.compute_kimchi_pair(date, ew)
        if (date,shop,d)==("2026-11-04","401","된장찌개"): r=X.compute_exchange_units("애호박된장찌개", ew, use_plaza_servings=False)
        if r is None: r=X.compute_exchange_units(it.get('calculationName',d), ew, use_plaza_servings=(shop=='105'))
        u={g:round(r['units'][g],2) for g in GR if r['units'][g]>0.004}
        out.append(f"  - {d} w={it['weight_g']}g ew={ew}g calc={it.get('calculationName','')} nutriDB={it.get('source')}:{it.get('db_name')} | matched={r['matched']} src={r.get('source')} → {r.get('matched_name')} | {u}")
        if r['matched']:
            for g in GR: tot[g]+=r['units'][g]
        for nm,grp,w,k,v in LOG:
            if k=='SKIP': out.append(f"        · {nm} [{grp}] {w}g → 제외")
            elif abs(v)>=0.15: out.append(f"        · {nm} [{grp}] {w}g → {k} +{v}")
    out.append(f"  => 재계산합 { {g:round(v,2) for g,v in tot.items()} }")
open(sys.argv[2],'w',encoding='utf-8').write('\n'.join(out))
print('done', len(out))
