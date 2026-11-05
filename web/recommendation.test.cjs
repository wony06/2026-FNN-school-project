const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const Score=require('./personal-score.js');
const View=require('./recommendation-view.js');
const read=name=>JSON.parse(fs.readFileSync(path.join(__dirname,name),'utf8'));
const normal=read('eer_exchange_targets.json');
const glycemic=read('glycemic_exchange_targets.json');
const profile={sex:'male',age:22,heightCm:170,weightKg:65,activity:1,mealCount:3};
const row=(main,properties={})=>({date:'2026-09-09',shop:'105',category:'한식',main,unmatched:[],
  kcal:450,protein:30,sugar:12,na:700,nrf:5,...properties});
const rows=[row('A',{protein:40,sugar:20,na:700,nrf:10,kcal:450}),
  row('B',{protein:30,sugar:5,na:300,nrf:20,kcal:550}),
  row('C',{protein:25,sugar:8,na:500,nrf:-3,kcal:350})];
const snapshot={entries:rows.map((r,i)=>({key:[r.date,r.shop,r.category,r.main],exchangeUnits:{
  grain:i+1,meat:2,veg:2,fat:1,unmatched:[]}}))};
const ranked=(context)=>View.rankVisibleMenus(Score.scoreMenus(rows,snapshot,context),'all',Score.compareMenus);

test('EER 식은 유지하고 2끼와 3끼의 한 끼 교환단위만 달라진다',()=>{
  const three=Score.createContext(profile,'lifestyle',normal,glycemic);
  const two=Score.createContext({...profile,mealCount:2},'lifestyle',normal,glycemic);
  assert.equal(three.eer,two.eer);
  assert.equal(three.roundedEer,two.roundedEer);
  three.mealTarget.forEach((v,i)=>assert.equal(two.mealTarget[i],v*1.5));
  assert.throws(()=>Score.createContext({...profile,mealCount:1},'lifestyle',normal,glycemic));
});

test('감량 기본 750, 목표 적자 계산, 1000 상한과 반올림 전 메뉴 열량 제한',()=>{
  const fallback=Score.createContext(profile,'weight_loss',normal,glycemic);
  const mild=Score.createContext(profile,'weight_loss',normal,glycemic,1);
  const capped=Score.createContext(profile,'weight_loss',normal,glycemic,10);
  assert.equal(fallback.deficit,750);
  assert.equal(mild.deficit,7000/30);
  assert.equal(capped.deficit,1000);
  assert.equal(fallback.mealEnergyLimit,(fallback.eer-750)/3);
  assert.equal(fallback.roundedEer,Math.floor((fallback.adjustedEer+50)/100)*100);
  assert.throws(()=>Score.createContext(profile,'weight_loss',normal,glycemic,-1));
  assert.throws(()=>Score.createContext({...profile,weightKg:35},'weight_loss',normal,glycemic,10),/범위 밖/);
  const boundary=rows.map((r,i)=>row(r.main,{...r,kcal:i===0?fallback.mealEnergyLimit:fallback.mealEnergyLimit+0.01}));
  const scored=Score.scoreMenus(boundary,snapshot,fallback);
  assert.equal(scored[0].recommendation.eligible,true);
  assert.equal(scored[1].recommendation.eligible,false);
});

test('혈당관리도 동일한 적합도 함수를 쓰되 다른 교환표를 사용한다',()=>{
  const life=Score.createContext(profile,'lifestyle',normal,glycemic);
  const blood=Score.createContext(profile,'glycemic',normal,glycemic);
  assert.equal(life.roundedEer,blood.roundedEer);
  assert.notDeepEqual(life.dailyTarget,blood.dailyTarget);
  assert.equal(Score.calculateDistance(life.mealTarget,life.mealTarget).distance,0);
  assert.equal(ranked(blood).filter(x=>x.rank!==null).length,3);
});

test('균형식은 NRF 원점수 내림차순, 저당·저나트륨은 각 영양값 오름차순',()=>{
  const names=goal=>ranked(Score.createContext(profile,goal,normal,glycemic)).map(x=>x.item.main);
  assert.deepEqual(names('balanced'),['B','A','C']);
  assert.deepEqual(names('low_sugar'),['B','C','A']);
  assert.deepEqual(names('low_sodium'),['B','C','A']);
  assert.equal(ranked(Score.createContext(profile,'balanced',normal,glycemic))[0].item.recommendation.metric,20);
});

test('고단백은 체중×0.4 이상만 순위에 넣고 그램으로 정렬한다',()=>{
  const context=Score.createContext(profile,'high_protein',normal,glycemic);
  assert.equal(context.proteinThreshold,26);
  const result=ranked(context);
  assert.deepEqual(result.map(x=>x.item.main),['A','B','C']);
  assert.deepEqual(result.map(x=>x.rank),[1,2,null]);
});

test('메뉴 교환단위 미매칭은 적합도 목표에서만 제외하고 원자료는 유지한다',()=>{
  const source=JSON.stringify(rows);
  const broken={entries:snapshot.entries.map((e,i)=>i===0?{...e,exchangeUnits:{...e.exchangeUnits,unmatched:['주요 반찬']}}:e)};
  const life=Score.scoreMenus(rows,broken,Score.createContext(profile,'lifestyle',normal,glycemic));
  const sugar=Score.scoreMenus(rows,broken,Score.createContext(profile,'low_sugar',normal,glycemic));
  assert.equal(life[0].recommendation.eligible,false);
  assert.equal(sugar[0].recommendation.eligible,true);
  assert.equal(JSON.stringify(rows),source);
});


test('거리 1 이상도 구분하며 세 교환단위 모드 모두 D 오름차순이다',()=>{
  for(const goal of ['lifestyle','weight_loss','glycemic']){
    const ctx=Score.createContext(profile,goal,normal,glycemic);
    const input=[row('가까움',{kcal:100}),row('중간',{kcal:100}),row('멀음',{kcal:100})];
    const exchanges={entries:input.map((r,i)=>({key:[r.date,r.shop,r.category,r.main],exchangeUnits:{
      ...Object.fromEntries(['grain','meat','veg','fat'].map((f,j)=>[f,ctx.mealTarget[j]*(2.1+i*.5)])),unmatched:[]}}))};
    const scored=Score.scoreMenus(input,exchanges,ctx);
    assert(scored.every(r=>r.recommendation.distance>1&&!('fit' in r.recommendation)));
    const result=View.rankVisibleMenus(scored,'all',Score.compareMenus);
    assert.deepEqual(result.map(r=>r.item.main),['가까움','중간','멀음']);
    assert.deepEqual(result.map(r=>r.rank),[1,2,3]);
  }
});

test('거리 동점은 실제 수치와 기계 오차만 사용하고 표시 반올림은 사용하지 않는다',()=>{
  const item=(main,distance,goal='lifestyle')=>row(main,{recommendation:{eligible:true,goal,metric:distance,distance}});
  const rounded=[item('A',1.00001),item('B',1.00002)];
  assert.equal(rounded[0].recommendation.distance.toFixed(4),rounded[1].recommendation.distance.toFixed(4));
  assert.deepEqual(View.rankVisibleMenus(rounded,'all',Score.compareMenus).map(x=>x.rank),[1,2]);
  const actual=[item('A',0.3),item('B',0.1+0.2),item('C',0.300000000001)];
  assert.deepEqual(View.rankVisibleMenus(actual,'all',Score.compareMenus).map(x=>x.rank),[1,1,3]);
  const chain=[item('A',1),item('B',1+6*Number.EPSILON),item('C',1+12*Number.EPSILON)];
  assert.deepEqual(View.rankVisibleMenus(chain,'all',Score.compareMenus).map(x=>x.rank),[1,1,3]);
  const sugar=[item('A',0.3,'low_sugar'),item('B',0.1+0.2,'low_sugar')];
  assert.deepEqual(View.rankVisibleMenus(sugar,'all',Score.compareMenus).map(x=>x.rank),[1,2]);
});

test('식당 탭은 기존 거리값을 재사용하고 미평가 메뉴에는 순위를 주지 않는다',()=>{
  const ctx=Score.createContext(profile,'lifestyle',normal,glycemic);
  const mixed=[...rows,row('다른식당',{shop:'204'}),row('미매칭',{unmatched:['X']})];
  const scored=Score.scoreMenus(mixed,snapshot,ctx);const original=JSON.stringify(scored);
  const all=View.rankVisibleMenus(scored,'all',Score.compareMenus),shop=View.rankVisibleMenus(scored,'105',Score.compareMenus);
  assert(shop.every(x=>x.item.shop==='105'));assert.equal(JSON.stringify(scored),original);
  for(const x of all.filter(x=>!x.item.recommendation.eligible))assert.equal(x.rank,null);
});
