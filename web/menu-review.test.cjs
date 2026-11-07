const {test}=require('node:test'),assert=require('node:assert/strict');
const Review=require('./menu-review.js');
const context=(goal,extra={})=>({goal,eer:1845,mealCount:3,mealTarget:[2,2,3,1],proteinThreshold:24,mealEnergyLimit:500,...extra});
const row=(extra={})=>({kcal:615,protein:24,sugar:6,na:2122,unmatched:[],recommendation:{goal:'lifestyle',actual:[3,1.5,3,1],eligible:true},...extra});
function describe(r,c,rank=1,peers=[r]){return Review.describe(r,c,rank,Review.createScope(peers,c));}
test('calories: positive, negative, equal, machine equality, tiny nonzero, two meals',()=>{
 for(const [kcal,text] of [[1545,'930kcal 높아요.'],[545,'70kcal 낮아요.'],[615,'열량과 같아요.'],[615+Number.EPSILON*615,'열량과 같아요.'],[615.01,'0.01kcal 높아요.']])assert(describe(row({kcal}),context('balanced')).energy.endsWith(text));
 assert(describe(row({kcal:615}),context('balanced',{mealCount:2})).energy.includes('307.5kcal 낮아요'));
});
test('weight loss uses committed adjusted meal limit, never original or rounded EER',()=>{
 assert.equal(describe(row({kcal:450}),context('weight_loss')).energy,'한 끼 목표 열량보다 50kcal 낮아요.');
});
test('exchange goals use their own targets; largest absolute difference and fixed tie order',()=>{
 for(const [goal,prefix] of [['lifestyle','한 끼 목표'],['weight_loss','조정된 한 끼 목표'],['glycemic','혈당관리 목표']])assert.equal(describe(row({recommendation:{goal,actual:[3,1,3,1]}}),context(goal)).goal,`${prefix}와 비교해 곡류군이 많아요.`);
 assert(describe(row(),context('lifestyle',{mealTarget:[3,3,3,1]})).goal.includes('어육류군이 적어요'));
 assert(describe(row({recommendation:{goal:'lifestyle',actual:[2,2,3,1+Number.EPSILON]}}),context('lifestyle')).goal.includes('일치해요'));
});
test('exchange missing/negative/unmatched is not an invented zero',()=>{
 for(const actual of [null,[2,null,3,1],[2,-1,3,1]])assert(describe(row({recommendation:{goal:'lifestyle',actual}}),context('lifestyle')).goal.includes('정보가 부족'));
 assert(describe(row({unmatched:['unknown']}),context('lifestyle')).goal.includes('정보가 부족'));
});
test('authoritative snapshot allows excluded allergy cards to be compared without scoring them',()=>{
 const r=row({date:'x',shop:'s',category:'c',main:'m',recommendation:null}),c=context('glycemic');
 const snapshot={entries:[{key:['x','s','c','m'],exchangeUnits:{grain:2,meat:2,veg:3,fat:1,unmatched:[]}}]};
 const scope=Review.createScope([],c,snapshot);
 assert(Review.describe(r,c,null,scope).goal.includes('일치해요'));
 snapshot.entries[0].exchangeUnits.unmatched=['x'];
 assert(Review.describe(r,c,null,scope).goal.includes('정보가 부족'));
});
test('balanced only reuses actual displayed rank, excludes unranked and stale-goal rows',()=>{
 const r=row({recommendation:{goal:'balanced',eligible:true}}),c=context('balanced');
 assert(describe(r,c,2).goal.includes('2위'));
 assert(!describe(r,c,null).goal.includes('null위'));
 assert(!describe(row(),c,1).goal.includes('1위'));
});
test('protein over, under, equal and real zero, independent of stale row goal',()=>{
 for(const [protein,text] of [[37.1,'13.1g 더 포함'],[20.9,'3.1g 부족'],[24,'24g을 충족'],[0,'24g 부족']]){
  const result=describe(row({protein,recommendation:{goal:'low_sodium',eligible:false}}),context('high_protein')).goal;
  assert(result.includes(text));assert(!result.includes('나트륨'));
 }
});
test('sugar/sodium actual minima, ties, differences and restaurant-specific scope',()=>{
 for(const [goal,field,unit,low,high] of [['low_sugar','sugar','g',6,9],['low_sodium','na','mg',2122,2161]]){
  const c=context(goal),a=row({[field]:low,recommendation:{goal,eligible:true}}),b=row({[field]:high,recommendation:{goal,eligible:true}}),tie=row({...a});
  const scope=Review.createScope([a,b,tie],c);
  for(const r of [a,tie])assert(Review.describe(r,c,1,scope).goal.includes('가장 낮아요'));
  assert(Review.describe(b,c,2,scope).goal.includes(`${high-low}${unit} 높아요`));
  assert(describe(b,c,1,[b]).goal.includes('가장 낮아요'));
 }
});
test('missing, actual 0, partial source totals, unrelated missing micros',()=>{
 const c=context('low_sugar'),zero=row({sugar:0,recommendation:{goal:'low_sugar',eligible:true}});
 assert(describe(zero,c).goal.includes('가장 낮아요. (0g)'));
 for(const r of [row({sugar:null}),row({sugar:0,missingFields:['sauce: sugar,vitA']}),row({itemDetails:[{matched:true,missing:['sugar'],contrib:{sugar:0}}]})])assert(describe(r,c).goal.includes('정보가 없어'));
 assert(Review.knownNutrient(row({missingFields:['sauce: vitA,vitC'],qualityFlags:['MISSING_NUTRIENTS_ZERO_FILLED_BY_SUPPLIED_CODE']}),'sugar'));
 assert(!Review.knownNutrient(row({itemDetails:[{matched:true,contrib:{protein:24}}]}),'sugar'));
 const missing=row({sugar:0,missingFields:['a: sugar'],recommendation:{goal:'low_sugar',eligible:true}});
 assert(describe(zero,c,1,[zero,missing]).goal.startsWith('영양정보가 확인된 추천 대상 메뉴 중'));
});
test('unknown calories/context/thresholds and non-comparison menus',()=>{
 assert(describe(row({kcal:null}),context('balanced')).energy.includes('열량 정보가 없어'));
 assert(describe(row(),null).energy.includes('목표 열량 정보가 없어'));
 assert(describe(row({protein:null}),context('high_protein')).goal.includes('단백질 정보가 없어'));
 assert(describe(row(),context('high_protein',{proteinThreshold:null})).goal.includes('목표 정보가 없어'));
 const r=row({sugar:1,recommendation:{goal:'low_sugar',eligible:false}});
 assert(describe(r,context('low_sugar')).goal.includes('추천 비교 대상에서 제외'));
});
test('presentation does not mutate input rows, context or snapshots',()=>{
 const r=row(),c=context('lifestyle'),s={entries:[]},before=JSON.stringify([r,c,s]);
 Review.describe(r,c,1,Review.createScope([r],c,s));assert.equal(JSON.stringify([r,c,s]),before);
});
