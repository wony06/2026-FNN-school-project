const test=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const Score=require('./personal-score.js'),Store=require('./profile-storage.js');
const read=name=>JSON.parse(fs.readFileSync(path.join(__dirname,name),'utf8'));
const normal=read('eer_exchange_targets.json'),glycemic=read('glycemic_exchange_targets.json');
const profile={sex:'male',age:22,heightCm:200,weightKg:100,activity:1,mealCount:3};
const originalEer=p=>{
 const h=p.heightCm/100,pa=(p.sex==='male'?[1,1.11,1.25,1.48]:[1,1.12,1.27,1.45])[p.activity];
 return p.sex==='male'?662-9.53*p.age+pa*(15.91*p.weightKg+539.6*h):354-6.91*p.age+pa*(9.36*p.weightKg+726*h);
};
const near=(actual,expected)=>assert(Math.abs(actual-expected)<1e-9,`${actual} != ${expected}`);

test('BMI 25 미만은 성별·PA·2끼/3끼와 관계없이 기존 EER과 동일하다',()=>{
 for(const sex of ['male','female'])for(const activity of [0,1,2,3])for(const mealCount of [2,3]){
  const p={...profile,sex,activity,mealCount,weightKg:99.6};
  const result=Score.calculateEer(p);
  assert.equal(result.eer,originalEer(p));assert.equal(result.eerWeightKg,p.weightKg);
  assert.equal(result.adjustedWeightKg,null);
 }
});

test('BMI 정확히 25에서 남녀 IBW와 조정체중을 구분하고 원본을 덮어쓰지 않는다',()=>{
 for(const [sex,ideal,adjusted] of [['male',88,91],['female',84,88]]){
  const p={...profile,sex};const before=JSON.stringify(p),result=Score.calculateEer(p);
  assert.equal(result.bmi,25);assert.equal(result.idealWeightKg,ideal);
  assert.equal(result.adjustedWeightKg,adjusted);assert.equal(result.eerWeightKg,adjusted);
  assert.equal(result.actualWeightKg,100);assert.equal(JSON.stringify(p),before);
  assert.equal(result.eer,originalEer({...p,weightKg:adjusted}));
 }
});

test('BMI 25 초과에도 동일한 조정식을 쓰며 EER에 임의 상한을 두지 않는다',()=>{
 const p={...profile,weightKg:180,activity:3},result=Score.calculateEer(p);
 near(result.eerWeightKg,88+(180-88)/4);assert(result.eer>3000);
 assert.equal(result.eer,originalEer({...p,weightKg:111}));
 assert.equal(Score.createContext(p,'balanced',normal,glycemic).eer,result.eer);
});

test('반올림된 BMI 대신 원래 BMI로 18.5·23·25 경계를 판단한다',()=>{
 for(const [bmi,allowed,category] of [[18.49,false,'underweight'],[18.5,false,'normal'],[22.9,false,'normal'],
  [22.9999,false,'normal'],[23,true,'pre_obesity'],[24.9,true,'pre_obesity'],[25,true,'obesity']]){
  const p={...profile,weightKg:bmi*4},result=Score.weightLossEligibility(p);
  near(result.bmi,bmi);assert.equal(result.allowed,allowed);assert.equal(result.category,category);
 }
 assert.equal(Score.calculateWeightBasis({...profile,weightKg:24.9999*4}).adjustedWeightKg,null);
});

test('키·체중 누락·0·음수·비유한 값은 BMI와 EER에서 거부한다',()=>{
 for(const field of ['heightCm','weightKg'])for(const value of [undefined,null,0,-1,NaN,Infinity]){
  const p={...profile,[field]:value};assert.throws(()=>Score.calculateBmi(p));assert.throws(()=>Score.calculateEer(p));
 }
});

test('160cm의 정확한 BMI 18.5·23·25는 이진수 연산 오차로 잘못 분류되지 않는다',()=>{
 const p={...profile,heightCm:160};
 assert.equal(Score.weightLossEligibility({...p,weightKg:47.36}).category,'normal');
 assert.equal(Score.weightLossEligibility({...p,weightKg:58.88}).allowed,true);
 near(Score.calculateWeightBasis({...p,weightKg:64}).eerWeightKg,58.24);
 assert.equal(Score.weightLossEligibility({...p,weightKg:58.8799}).allowed,false);
 assert.equal(Score.calculateWeightBasis({...p,weightKg:63.9999}).adjustedWeightKg,null);
});

test('저체중·정상체중은 감량 컨텍스트 생성 자체를 차단하고 다른 목표는 허용한다',()=>{
 for(const [bmi,words] of [[18,'저체중'],[18.5,'정상범위'],[22.9,'정상범위']]){
  const p={...profile,weightKg:bmi*4};
  assert.throws(()=>Score.createContext(p,'weight_loss',normal,glycemic),error=>error.message.includes(words));
  for(const goal of ['lifestyle','glycemic','balanced','high_protein','low_sugar','low_sodium'])
   assert.equal(Score.createContext(p,goal,normal,glycemic).goal,goal);
 }
 for(const bmi of [23,24.9,25])assert.equal(Score.createContext({...profile,weightKg:bmi*4},'weight_loss',normal,glycemic).goal,'weight_loss');
});

test('새 EER을 반올림·교환표·2끼/3끼 목표·감량 상한에 그대로 전달한다',()=>{
 for(const mealCount of [2,3])for(const goal of ['lifestyle','glycemic','weight_loss']){
  const p={...profile,weightKg:120,mealCount},ctx=Score.createContext(p,goal,normal,glycemic);
  assert.equal(ctx.eer,Score.calculateEer(p).eer);assert.equal(ctx.weightKg,120);assert.equal(ctx.eerWeightKg,96);
  const energy=ctx.eer-(goal==='weight_loss'?750:0);
  assert.equal(ctx.adjustedEer,energy);assert.equal(ctx.roundedEer,Math.floor((energy+50)/100)*100);
  const row=(goal==='glycemic'?glycemic:normal).dailyExchanges[ctx.roundedEer];
  const daily=[row[0],row[1]+row[2],row[3],row[4]];
  assert.deepEqual(ctx.dailyTarget,daily);assert.deepEqual(ctx.mealTarget,daily.map(v=>v/mealCount));
  if(goal==='weight_loss')assert.equal(ctx.mealEnergyLimit,energy/mealCount);
 }
 const ctx=Score.createContext(profile,'weight_loss',normal,glycemic,10);assert.equal(ctx.deficit,1000);
});

test('고단백 기준과 저장 정보에는 조정체중 대신 실제체중을 유지한다',()=>{
 const ctx=Score.createContext(profile,'high_protein',normal,glycemic);
 assert.equal(ctx.eerWeightKg,91);assert.equal(ctx.weightKg,100);assert.equal(ctx.proteinThreshold,40);
 const items=new Map(),storage={getItem:k=>items.get(k)??null,setItem:(k,v)=>items.set(k,v),removeItem:k=>items.delete(k)};
 const saved={sex:'male',age:'22',heightCm:'200',weightKg:'100',activity:'1',mealCount:'3',goal:'weight_loss',allergies:[]};
 Store.writeSaved(storage,{...saved,eerWeightKg:91},true);
 assert.deepEqual(Store.readSaved(storage),saved);assert.equal(Store.resumeStep(saved),4);
 assert(!storage.getItem(Store.KEY).includes('eerWeightKg'));
 const restricted={...saved,weightKg:'80'};Store.writeSaved(storage,restricted,true);const before=storage.getItem(Store.KEY);
 assert.equal(Store.resumeStep(Store.readSaved(storage)),3);assert.equal(storage.getItem(Store.KEY),before);
 assert.equal(Store.readSaved(storage).weightKg,'80');
});

test('새 EER 기준 한 끼 열량 초과 제외와 정규화 거리 정렬은 기존 방식을 유지한다',()=>{
 const ctx=Score.createContext(profile,'weight_loss',normal,glycemic);
 const row=(main,kcal)=>({date:'2026-11-20',shop:'204',category:'정식',main,kcal,unmatched:[]});
 const rows=[row('목표',ctx.mealEnergyLimit),row('초과',ctx.mealEnergyLimit+0.001)];
 const snapshot={entries:rows.map(r=>({key:[r.date,r.shop,r.category,r.main],exchangeUnits:{
  ...Object.fromEntries(['grain','meat','veg','fat'].map((f,i)=>[f,ctx.mealTarget[i]])),unmatched:[]}}))};
 const scored=Score.scoreMenus(rows,snapshot,ctx);
 assert.equal(scored[0].recommendation.distance,0);assert.equal(scored[0].recommendation.eligible,true);
 assert.equal(scored[1].recommendation.eligible,false);assert(scored[1].recommendation.reason.includes('초과'));
});
