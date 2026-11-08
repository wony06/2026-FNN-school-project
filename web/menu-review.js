(function(root){
  'use strict';
  // Presentation only: never changes eligibility, metrics, or ranks.
  const GROUPS=['grain','meat','veg','fat'];
  const LABELS=['곡류군','어육류군','채소군','지방군'];
  const EXCHANGE=new Set(['lifestyle','weight_loss','glycemic']);
  const valid=v=>Number.isFinite(v)&&v>=0;
  const same=(a,b)=>Math.abs(a-b)<=8*Number.EPSILON*Math.max(1,Math.abs(a),Math.abs(b));
  const key=row=>JSON.stringify([row.date,row.shop,row.category,row.main]);
  function format(value){
    // Retain a visible nonzero difference even when it is below one decimal.
    const options=value!==0&&Math.abs(value)<0.05 ? {maximumSignificantDigits:3} : {maximumFractionDigits:1};
    return new Intl.NumberFormat('ko-KR',options).format(value);
  }
  function knownNutrient(row,field){
    if(!valid(row?.[field])||(row.unmatched?.length??0)>0) return false;
    // Some legacy totals were zero-filled; use per-nutrient evidence, not the
    // broad quality flag (which can refer only to unrelated micronutrients).
    if((row.missingFields??[]).some(entry=>String(entry).split(':').pop().split(',').map(v=>v.trim()).includes(field)))return false;
    return !(row.itemDetails??[]).some(part=>part.matched===false||
      (part.missing??[]).includes(field)||
      (part.contrib&&(!Object.hasOwn(part.contrib,field)||!valid(part.contrib[field]))));
  }
  function createScope(rows,context,snapshot){
    const eligible=rows.filter(row=>row.recommendation?.eligible===true&&row.recommendation.goal===context?.goal);
    const minima={};
    for(const field of ['sugar','na']){
      const known=eligible.filter(row=>knownNutrient(row,field));
      minima[field]={value:known.length?Math.min(...known.map(row=>row[field])):null,partial:known.length!==eligible.length};
    }
    return {context,eligible:new Set(eligible),minima,exchangeIndex:new Map((snapshot?.entries??[]).map(entry=>[JSON.stringify(entry.key),entry.exchangeUnits]))};
  }
  function exchangeReview(row,context,scope){
    const rec=row.recommendation;
    const units=scope?.exchangeIndex.get(key(row))??row.friendExchangeUnits;
    const actual=units?GROUPS.map(f=>units[f]):rec?.goal===context.goal?rec.actual:null;
    const target=context.mealTarget;
    if((row.unmatched?.length??0)>0||(units?.unmatched?.length??0)>0||
      !Array.isArray(actual)||!Array.isArray(target)||actual.length!==4||target.length!==4||
      ![...actual,...target].every(valid))return '식품군 정보가 부족해 목표 구성을 비교할 수 없어요.';
    let largest=-1,best=0;
    for(let i=0;i<4;i++){
      if(same(actual[i],target[i]))continue;
      const diff=Math.abs(actual[i]-target[i]);
      if(largest<0||(diff>best&&!same(diff,best))){largest=i;best=diff;}
    }
    if(largest<0)return '식품군별 교환단위가 한 끼 목표와 일치해요.';
    const prefix={lifestyle:'한 끼 목표',weight_loss:'조정된 한 끼 목표',glycemic:'혈당관리 목표'}[context.goal];
    return `${prefix}와 비교해 ${LABELS[largest]}이 ${actual[largest]>target[largest]?'많아요':'적어요'}.`;
  }
  function relativeReview(row,field,scope){
    const label=field==='sugar'?'총당류':'나트륨',unit=field==='sugar'?'g':'mg';
    if(!knownNutrient(row,field))return `${label} 정보가 없어 다른 메뉴와 비교할 수 없어요.`;
    if(!scope?.eligible.has(row))return `${label} ${format(row[field])}${unit}이며, 추천 비교 대상에서 제외된 메뉴예요.`;
    const minimum=scope.minima[field];
    if(!valid(minimum.value))return `${label} 비교에 필요한 메뉴 정보가 없어요.`;
    const prefix=minimum.partial?'영양정보가 확인된 추천 대상 메뉴 중':'조회한 메뉴 중';
    // Ranking uses exact nutrient values; equal displayed rounding is not a tie.
    if(row[field]===minimum.value)return `${prefix} ${label} 함량이 가장 낮아요. (${format(row[field])}${unit})`;
    return `${label} ${format(row[field])}${unit}으로, ${minimum.partial?'영양정보가 확인된 ':''}최저 함량 메뉴보다 ${format(row[field]-minimum.value)}${unit} 높아요.`;
  }
  function goalReview(row,context,rank,scope){
    if(!context)return '영양 목표를 선택하면 메뉴별 비교를 확인할 수 있어요.';
    if(EXCHANGE.has(context.goal))return exchangeReview(row,context,scope);
    if(context.goal==='balanced')return Number.isInteger(rank)&&rank>0&&row.recommendation?.eligible&&row.recommendation.goal===context.goal
      ? `조회한 메뉴 중 NRF6.3 영양밀도 평가에서 ${rank}위를 기록했어요.`
      : '추천 비교 대상에서 제외되어 NRF6.3 순위를 표시할 수 없어요.';
    if(context.goal==='high_protein'){
      if(!knownNutrient(row,'protein'))return '단백질 정보가 없어 목표와 비교할 수 없어요.';
      const target=context.proteinThreshold;
      if(!valid(target))return '한 끼 단백질 목표 정보가 없어 비교할 수 없어요.';
      if(same(row.protein,target))return `한 끼 단백질 목표 ${format(target)}g을 충족해요.`;
      if(row.protein>target)return `한 끼 단백질 목표 ${format(target)}g보다 ${format(row.protein-target)}g 더 포함되어 있어요.`;
      return `한 끼 단백질 목표 ${format(target)}g까지 ${format(target-row.protein)}g 부족해요.`;
    }
    if(context.goal==='low_sugar')return relativeReview(row,'sugar',scope);
    if(context.goal==='low_sodium')return relativeReview(row,'na',scope);
    return '선택한 영양 목표를 확인해 주세요.';
  }
  function energyReview(row,context){
    if(!knownNutrient(row,'kcal'))return '열량 정보가 없어 한 끼 목표와 비교할 수 없어요.';
    const target=context?.goal==='weight_loss'?context.mealEnergyLimit:
      [2,3].includes(context?.mealCount)&&Number.isFinite(context?.eer)?context.eer/context.mealCount:null;
    if(!Number.isFinite(target)||target<=0)return '한 끼 목표 열량 정보가 없어 비교할 수 없어요.';
    const diff=row.kcal-target;
    if(same(row.kcal,target))return '한 끼 목표 열량과 같아요.';
    return `한 끼 목표 열량보다 ${format(Math.abs(diff))}kcal ${diff>0?'높아요':'낮아요'}.`;
  }
  function describe(row,context,rank,scope){
    return {goal:goalReview(row,context,rank,scope),energy:energyReview(row,context)};
  }
  const api={describe,createScope,knownNutrient};
  if(typeof module!=='undefined'&&module.exports)module.exports=api;else root.MenuReview=api;
})(globalThis);
