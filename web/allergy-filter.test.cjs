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

test('449개 식단 키가 정확히 1:1 연결되고 중복 키는 거부한다',()=>{
  assert.equal(index.size,449);
  assert(rows.every(r=>index.has(key(r))));
  assert.throws(()=>Filter.buildIndex({...data,meals:[...data.meals,data.meals[0]]}),/중복/);
});
test('우유·새우·밀·조개류 제외 수와 다중 선택 OR 동작',()=>{
  for(const [code,count] of [[2,217],[9,205],[6,278],[18,213]])assert.equal(Filter.partition(rows,[code],index).excluded.length,count);
  const one=Filter.partition(rows,[2],index),two=Filter.partition(rows,[9],index);
  const union=new Set([...one.excluded,...two.excluded].map(key));
  const both=Filter.partition(rows,[2,9],index);
  assert.equal(both.excluded.length,union.size);
  assert(both.excluded.every(r=>union.has(key(r))));
  assert.equal(both.kept.length+both.excluded.length,449);
});
test('고구마치즈돈까스 조개류 1/2 기록은 미확인으로 보존하고 자동 제외하지 않는다',()=>{
  const cutlets=rows.filter(r=>r.main==='고구마치즈돈까스');
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
