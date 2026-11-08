const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs'),path=require('node:path');
const Filter=require('./allergy-filter.js');
const Score=require('./personal-score.js');
const View=require('./recommendation-view.js');
const Rice=require('./instant-rice.js');
const read=f=>JSON.parse(fs.readFileSync(path.join(__dirname,f),'utf8'));
const data=read('allergy-data.json'),rows=read('site_data.json'),index=Filter.buildIndex(data);
const key=Filter.key;

test('검토된 식단 키가 정확히 1:1 연결되고 중복 키는 거부한다',()=>{
  assert.equal(index.size,data.meals.length);
  const currentKeys=new Set(rows.map(key));
  assert([...index.keys()].every(k=>currentKeys.has(k)));
  assert.throws(()=>Filter.buildIndex({...data,meals:[...data.meals,data.meals[0]]}),/중복/);
});
test('우유·새우·밀·조개류 제외 수와 다중 선택 OR 동작',()=>{
  for(const [code,count] of [[2,210],[9,205],[6,279],[18,213]])assert.equal(Filter.partition(rows,[code],index).excluded.length,count);
  const one=Filter.partition(rows,[2],index),two=Filter.partition(rows,[9],index);
  const union=new Set([...one.excluded,...two.excluded].map(key));
  const both=Filter.partition(rows,[2,9],index);
  assert.equal(both.excluded.length,union.size);
  assert(both.excluded.every(r=>union.has(key(r))));
  assert.equal(both.kept.length+both.excluded.length,rows.length);
});
test('고구마치즈돈까스 조개류 1/2 기록은 미확인으로 보존하고 자동 제외하지 않는다',()=>{
  const cutlets=rows.filter(r=>r.main==='고구마치즈돈까스'&&index.has(key(r)));
  assert.equal(cutlets.length,22);
  for(const r of cutlets){
    const a=Filter.assess(r,new Set([18]),index);
    assert.equal(a.excluded,false);
    assert(a.entry.suppressed.some(s=>s.code===18&&s.labeledRecords===1&&s.totalRecords===2&&s.state==='미확인'));
    for(const s of a.entry.suppressed)assert(s.recordIds.every(id=>data.sourceRecords[id]));
  }
});
test('반찬에 명시된 조개류 근거와 다른 음식의 NEIS 조개류는 유지한다',()=>{
  const example=data.meals.find(m=>m.allergens.some(a=>a.code===18&&a.nameEvidence.some(e=>e.component!==m.key[3])));
  assert(example,'실제 반찬 명칭의 조개류 사례가 있어야 함');
  const row=rows.find(r=>key(r)===JSON.stringify(example.key));
  assert(Filter.partition([row],[18],index).excluded.length===1);
  const neis=data.meals.find(m=>m.allergens.some(a=>a.code===18&&a.neisEvidence.some(e=>!e.component.includes('돈까스')&&!e.component.includes('돈가스'))));
  assert(neis);
});
test('52개 통합 보류와 신규 미연결 메뉴는 미확인으로 유지한다',()=>{
  const held=data.meals.filter(m=>m.state==='choice_withheld');
  assert.equal(held.length,52);
  const selected=new Set(data.allergens.map(a=>a.code));
  for(const e of held){
    const r=rows.find(r=>key(r)===JSON.stringify(e.key));
    const a=Filter.assess(r,selected,index);assert(!a.excluded&&a.requiresIngredientCheck);
  }
  const future={...rows[0],date:'2026-11-30',main:'미등록메뉴'};
  const a=Filter.assess(future,selected,index);
  assert.equal(a.state,'missing_estimate');assert(!a.excluded&&a.requiresIngredientCheck);
  for(const row of rows.filter(r=>!index.has(key(r)))){
    const unreviewed=Filter.assess(row,selected,index);
    assert.equal(unreviewed.state,'missing_estimate');
    assert(!unreviewed.excluded&&unreviewed.requiresIngredientCheck);
  }
});
test('미선택은 원래 행을 그대로 반환하며 7가지 추천 결과가 동일하다',()=>{
  const original=read('site_data.json'),snapshot=read('menu_exchange_snapshot.json');
  Rice.apply(original,snapshot);
  assert.equal(Filter.partition(original,[],index).kept,original);
  const normal=read('eer_exchange_targets.json'),glycemic=read('glycemic_exchange_targets.json');
  const profile={sex:'male',age:22,heightCm:170,weightKg:65,activity:1,mealCount:3};
  for(const goal of ['lifestyle','weight_loss','glycemic','balanced','high_protein','low_sugar','low_sodium']){
    const ctx=Score.createContext(profile,goal,normal,glycemic);
    const baseline=Score.scoreMenus(original,snapshot,ctx);
    const noFilter=Score.scoreMenus(Filter.partition(original,[],index).kept,snapshot,ctx);
    assert.deepEqual(noFilter,baseline);
    const filtered=Filter.partition(original,[2,9],index);
    const scored=Score.scoreMenus(filtered.kept,snapshot,ctx);
    const lookup=new Map(baseline.map(r=>[key(r),r.recommendation]));
    for(const row of scored)assert.deepEqual(row.recommendation,lookup.get(key(row)));
    const ranked=View.rankVisibleMenus(scored,'all',Score.compareMenus);
    assert(ranked.every(r=>!filtered.excluded.some(e=>key(e)===key(r.item))));
  }
});


test('승인한 10개 연결만 보류하며 원본 기록과 다른 반찬의 활성 근거를 보존한다',()=>{
  const pairs=new Set(['마카로니샐러드:4','마카로니샐러드:16','마카로니샐러드:17','식혜:11','무말랭이무침:2','식혜:12','계란말이:10','콘샐러드:8','계란말이:15','계란말이:16']);
  const observed=new Set();let otherEvidence=0;
  for(const meal of data.meals){
    for(const e of meal.suppressed.filter(e=>e.policy==='reviewed-reference-hold-v2')){
      observed.add(`${e.reference}:${e.code}`);
      assert(pairs.has(`${e.reference}:${e.code}`));assert.equal(e.state,'미확인');
      assert(e.recordIds.length && e.recordIds.every(id=>data.sourceRecords[id]));
      const active=meal.allergens.find(a=>a.code===e.code);
      if(active){otherEvidence++;assert(active.nameEvidence.length || active.neisEvidence.some(n=>n.reference!==e.reference));}
    }
    assert(!meal.suppressed.some(e=>e.reference==='배추김치'&&e.code===18));
  }
  assert.deepEqual(observed,pairs);assert(otherEvidence>0);
});

test('명칭 단서 보완은 번역 명칭에만 적용되고 굴라쉬 오인식은 제거된다',()=>{
  const names=data.meals.flatMap(m=>m.allergens.flatMap(a=>a.nameEvidence.map(e=>({code:a.code,...e}))));
  assert(!names.some(e=>e.code===18&&e.component.includes('굴라쉬')));
  for(const [term,code] of [['부타동',10],['비프',16],['소불고기',16],['소머리',16],['포크',10]]){
    assert(names.some(e=>e.code===code&&e.component.includes(term)));
  }
  for(const e of names)assert(!e.terms.some(t=>['햄','마요','베이컨','크림'].includes(t)));
});


test('사용자 제공 돼지고기 단서와 미사용 답변은 출처를 구분해 반영한다',()=>{
  for(const component of ['목살김치찌개','고추잡채덮밥']){
    const examples=data.meals.filter(m=>m.allergens.some(a=>a.code===10&&a.nameEvidence.some(e=>e.component===component&&e.provenance?.type==='user_report')));
    assert(examples.length>0);
  }
  const pairs=[['식혜',12],['계란말이',10],['계란말이',15],['계란말이',16],['콘샐러드',8]];
  for(const [reference,code] of pairs){
    const held=data.meals.flatMap(m=>m.suppressed).filter(e=>e.reference===reference&&e.code===code);
    assert(held.length>0);assert(held.every(e=>e.reviewSource.includes('사용자 제공')));
    assert(data.meals.every(m=>!m.allergens.some(a=>a.code===code&&a.neisEvidence.some(e=>e.reference===reference))));
  }
  assert(data.meals.every(m=>m.actualIngredientsConfirmed===false));
});


test('2차 사용자 검토는 원재료 단서와 조리법 미확인 후보를 구분한다',()=>{
  const reviews=data.meals.flatMap(m=>m.userReviewNotes??[]);
  for(const subject of ['통살치킨까스','놀부부대찌개','참치야채비빔밥','새우튀김알밥','대패삼겹덮밥'])assert(reviews.some(r=>r.subject===subject));
  assert(reviews.filter(r=>r.subject==='참치야채비빔밥').every(r=>r.confirmed.length===1&&r.confirmed[0]==='마요네즈 없음'));
  const pork=data.meals.flatMap(m=>m.allergens).filter(a=>a.code===10).flatMap(a=>a.nameEvidence);
  assert(pork.some(e=>e.component==='대패삼겹덮밥'&&e.provenance?.type==='user_report'));
  // Candidate references from recipe review cannot silently become accepted code sources.
  for(const meal of data.meals)for(const a of meal.allergens){
    assert(!a.neisEvidence.some(e=>e.component==='통살치킨까스'&&e.reference==='치킨가스'));
    assert(!a.neisEvidence.some(e=>e.component==='놀부부대찌개'&&e.reference==='부대찌개'));
    assert(!a.neisEvidence.some(e=>e.component==='대패삼겹덮밥'&&e.reference==='#대패삼겹살덮밥'));
  }
});


test('3차 사용자 답변의 확실한 재료만 적용하고 해물 추정과 모르는 패티는 보류한다',()=>{
  const reviews=data.meals.flatMap(m=>m.userReviewNotes??[]);
  const seafood=reviews.filter(r=>r.subject==='몽글순두부찌개');
  assert(seafood.length>0);assert(seafood.every(r=>r.tentative.length&&r.automaticCodeAddition.length===0));
  const named=data.meals.flatMap(m=>m.allergens.flatMap(a=>a.nameEvidence.map(e=>({code:a.code,...e}))));
  for(const [component,code] of [['왕돈가스',10],['베이컨마늘볶음밥',10],['베이컨마늘볶음밥',1],['차돌김치찌개',16]]){
    assert(named.some(e=>e.code===code&&e.component===component&&e.provenance?.type==='user_report'));
  }
  assert(!named.some(e=>e.component==='몽글순두부찌개'&&[9,17,18].includes(e.code)&&e.provenance?.type==='user_report'));
  assert(!named.some(e=>e.component==='하와이안함박스테이크'&&[10,16].includes(e.code)&&e.provenance?.type==='user_report'));
});
