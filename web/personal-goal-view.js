(function(root){
  'use strict';
  // A read-only view of the existing targets and authoritative menu exchanges.
  const GOALS={
    lifestyle:{label:'라이프스타일 유지',description:'한 끼 목표 식품군 구성과 메뉴 구성을 비교한 결과입니다.'},
    weight_loss:{label:'체중감량',description:'감량 목표를 반영한 한 끼 기준과 메뉴 구성을 비교한 결과입니다.'},
    glycemic:{label:'혈당관리',description:'혈당관리용 식품교환표 기준과 메뉴 구성을 비교한 결과입니다.'}
  };
  const FIELDS=['grain','meat','veg','fat'];
  const LABELS=['곡류군','어육류군','채소군','지방군'];
  const valid=value=>Number.isFinite(value)&&value>=0;
  const same=(a,b)=>Math.abs(a-b)<=8*Number.EPSILON*Math.max(1,Math.abs(a),Math.abs(b));
  const format=value=>new Intl.NumberFormat('ko-KR',{maximumFractionDigits:2}).format(value);
  function formatDifference(value){
    if(value===null)return '미확인';
    if(value===0)return '0.0';
    const options=Math.abs(value)<.005?{maximumSignificantDigits:2}:{minimumFractionDigits:1,maximumFractionDigits:2};
    return (value>0?'+':'−')+new Intl.NumberFormat('ko-KR',options).format(Math.abs(value));
  }
  function model(row,context,scope){
    const goal=GOALS[context?.goal];
    if(!goal)return null;
    const key=JSON.stringify([row.date,row.shop,row.category,row.main]);
    const units=scope?.exchangeIndex?.get(key)??row.friendExchangeUnits;
    const rec=row.recommendation;
    const candidate=units?FIELDS.map(field=>units[field]):rec?.goal===context.goal?rec.actual:null;
    const actualKnown=Array.isArray(candidate)&&candidate.length===4&&candidate.every(valid)&&
      !(row.unmatched?.length)&&!(units?.unmatched?.length);
    const target=context.mealTarget;
    const targetKnown=Array.isArray(target)&&target.length===4&&target.every(valid);
    const groups=FIELDS.map((field,i)=>{
      const wanted=targetKnown?target[i]:null,actual=actualKnown?candidate[i]:null;
      return {field,label:LABELS[i],target:wanted,actual,
        difference:wanted===null||actual===null?null:same(actual,wanted)?0:actual-wanted};
    });
    // A single visual scale for all eight bars; this is not a nutrition threshold.
    const max=Math.max(0,...groups.flatMap(g=>[g.target,g.actual].filter(valid)));
    for(const g of groups){g.targetWidth=max&&g.target!==null?g.target/max*100:0;g.actualWidth=max&&g.actual!==null?g.actual/max*100:0;}
    const energy=context.goal==='weight_loss'?context.mealEnergyLimit:
      Number.isFinite(context.eer)&&[2,3].includes(context.mealCount)?context.eer/context.mealCount:null;
    return {goal:context.goal,label:goal.label,description:goal.description,
      mealEnergy:Number.isFinite(energy)&&energy>0?energy:null,groups,
      incomplete:!actualKnown||!targetKnown};
  }
  function render(row,context,scope){
    const data=model(row,context,scope);
    if(!data)return '';
    const series=(label,value,width,type)=>`<div class="exchange-series"><span class="exchange-series-label">${label}</span><span class="exchange-track" aria-hidden="true"><i class="exchange-fill ${type}" style="width:${width}%"></i></span><span class="exchange-value">${value===null?'미확인':format(value)}</span></div>`;
    return `<details class="personal-goal-details">
      <summary>개인영양목표 상세보기<span class="exchange-toggle" aria-hidden="true"></span></summary>
      <div class="personal-goal-body">
        <div class="exchange-heading"><strong>${data.label}</strong><span>한 끼 목표 열량 <b>${data.mealEnergy===null?'미확인':format(data.mealEnergy)+' kcal'}</b></span></div>
        <p class="exchange-description">${data.description}</p>
        <div class="exchange-chart-caption"><span>식품교환표 기반 비교 · 단위: 교환단위</span><span>차이 = 실제 − 목표</span></div>
        <div class="exchange-chart" aria-label="4개 식품군의 목표와 실제 메뉴 교환단위 비교">
          ${data.groups.map(g=>`<div class="exchange-row" data-group="${g.field}"><h4>${g.label}</h4><div class="exchange-bars">${series('목표',g.target,g.targetWidth,'is-target')}${series('메뉴',g.actual,g.actualWidth,'is-actual')}</div><div class="exchange-difference"><small>차이</small><span>${formatDifference(g.difference)}</span></div></div>`).join('')}
        </div>
        <p class="exchange-footnote">회색은 목표, 파란색은 실제 메뉴입니다. 모든 막대는 같은 눈금으로 표시합니다.${data.incomplete?' 미확인 교환단위는 0으로 채우지 않고 비교를 보류합니다.':''}</p>
      </div>
    </details>`;
  }
  const api={model,render};
  if(typeof module!=='undefined'&&module.exports)module.exports=api;else root.PersonalGoalView=api;
})(globalThis);
