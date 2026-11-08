const {test}=require('node:test'),assert=require('node:assert/strict');
const View=require('./personal-goal-view.js');
const ctx=goal=>({goal,mealTarget:[2,2,3,1],eer:1845,mealCount:3,mealEnergyLimit:500});
const row=()=>({unmatched:[],recommendation:{goal:'lifestyle',actual:[3,1.5,3,0]}});
test('only the three personal goals have disclosures, each with its own description',()=>{
 for(const [goal,words] of [['lifestyle','한 끼 목표 식품군'],['weight_loss','감량 목표를 반영'],['glycemic','혈당관리용 식품교환표']])assert(View.render(row(),ctx(goal)).includes(words));
 for(const goal of ['balanced','high_protein','low_sugar','low_sodium',null])assert.equal(View.render(row(),ctx(goal)),'');
});
test('unaltered exchange values, signed differences, consistent bar scale, and real zero',()=>{
 const model=View.model(row(),ctx('lifestyle'));
 assert.deepEqual(model.groups.map(g=>[g.target,g.actual,g.difference]),[[2,3,1],[2,1.5,-.5],[3,3,0],[1,0,-1]]);
 assert.equal(model.groups[0].actualWidth,100);assert.equal(model.groups[1].actualWidth,50);assert.equal(model.groups[3].actualWidth,0);
 assert.equal(model.groups[0].targetWidth,model.groups[1].targetWidth);
 const html=View.render(row(),ctx('lifestyle'));for(const s of ['+1.0','−0.5','0.0'])assert(html.includes(s));
});
test('reuse ordinary two/three-meal energy and weight-loss adjusted limit',()=>{
 assert.equal(View.model(row(),ctx('lifestyle')).mealEnergy,615);
 assert.equal(View.model(row(),{...ctx('glycemic'),mealCount:2}).mealEnergy,922.5);
 assert.equal(View.model(row(),ctx('weight_loss')).mealEnergy,500);
});
test('authoritative exchange snapshot also supports unranked allergy cards',()=>{
 const r={date:'d',shop:'s',category:'c',main:'m',unmatched:[]};
 const units={grain:3,meat:1.5,veg:3,fat:0,unmatched:[]};
 const scope={exchangeIndex:new Map([[JSON.stringify(['d','s','c','m']),units]])};
 assert.deepEqual(View.model(r,ctx('glycemic'),scope).groups.map(g=>g.actual),[3,1.5,3,0]);
 units.unmatched=['x'];assert(View.model(r,ctx('glycemic'),scope).groups.every(g=>g.actual===null&&g.difference===null));
});
test('missing/negative/stale data is not a zero, target can remain visible',()=>{
 for(const actual of [null,[3,null,3,0],[3,-1,3,0]]){
  const model=View.model({...row(),recommendation:{goal:'lifestyle',actual}},ctx('lifestyle'));
  assert(model.incomplete);assert(model.groups.every(g=>g.actual===null&&g.difference===null));assert.equal(model.groups[0].target,2);
 }
 assert(View.model(row(),ctx('glycemic')).incomplete);
 assert(View.model(row(),{...ctx('lifestyle'),mealTarget:null}).groups.every(g=>g.target===null&&g.difference===null));
});
test('machine-error equality only; tiny real difference stays visible; all zero safe',()=>{
 const r=row();r.recommendation.actual=[2+Number.EPSILON,2,3,1];
 assert(View.model(r,ctx('lifestyle')).groups.every(g=>g.difference===0));
 r.recommendation.actual[0]=2.0001;assert(View.render(r,ctx('lifestyle')).includes('+0.0001'));
 r.recommendation.actual=[0,0,0,0];const m=View.model(r,{...ctx('lifestyle'),mealTarget:[0,0,0,0]});
 assert(m.groups.every(g=>g.targetWidth===0&&g.actualWidth===0&&g.difference===0));
});
test('render does not mutate context or menu values',()=>{
 const r=row(),c=ctx('lifestyle'),before=JSON.stringify([r,c]);View.render(r,c);assert.equal(JSON.stringify([r,c]),before);
});
