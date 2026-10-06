(function(root){
  'use strict';
  const RULE_FLAG='USER_POLICY_INSTANT_RICE_200G';
  const RICE_SERVING_G=200;
  const NUTRIENTS=['kcal','protein','fat','carb','sugar','fiber','ca','fe','vitA','vitC','satFat','na'];
  const BENEFICIAL=[['protein',50],['fiber',28],['ca',1300],['fe',18],['vitA',900],['vitC',90]];
  const LIMITED=[['satFat',20],['sugar',125],['na',2300]];
  const EXPLICIT_RICE=['김밥','꼬마김밥','유부초밥'];
  const SERVED_RICE=new Set(['쌀밥','흑미밥','백미밥','잡곡밥','현미밥']);
  const RICE_GRAIN=2.857391304347826; // Existing MenuGen exchange result for cooked rice, 200 g.
  const NOTE='즉석메뉴 기본 밥공기 200g(사용자 확인 제공 규칙; 실측값 아님)';
  const round=(value,decimals)=>Math.round((value+Number.EPSILON)*10**decimals)/10**decimals;
  const key=row=>JSON.stringify([row.date,row.shop,row.category,row.main]);
  function nrf(totals){
    const scale=100/totals.kcal;
    const contribution=([field,dv])=>Math.min(totals[field]*scale/dv,1)*100;
    return round(BENEFICIAL.reduce((sum,entry)=>sum+contribution(entry),0)-LIMITED.reduce((sum,entry)=>sum+contribution(entry),0),1);
  }
  function apply(rows,snapshot){
    const template=rows.flatMap(row=>row.itemDetails||[])
      .find(item=>item.display==='쌀밥'&&item.source==='food_db'&&item.weight_g>0&&NUTRIENTS.every(field=>Number.isFinite(item.contrib?.[field])));
    if(!template) throw Error('즉석메뉴에 사용할 쌀밥 DB 기준 자료가 없습니다.');
    const entries=new Map(snapshot.entries.map(entry=>[JSON.stringify(entry.key),entry]));
    const added=[];
    for(const row of rows){
      if(row.shop!=='105'||row.category!=='즉석') continue;
      if(!Array.isArray(row.itemDetails)) throw Error(`구성 음식 자료 없음: ${key(row)}`);
      if(row.itemDetails.some(item=>SERVED_RICE.has(item.display))) continue;
      if((row.components||[]).some(name=>EXPLICIT_RICE.some(rice=>name.includes(rice)))) continue;
      const entry=entries.get(key(row));
      if(!entry) throw Error(`교환단위 자료 없음: ${key(row)}`);
      const rice=JSON.parse(JSON.stringify(template));
      delete rice.photo_evidence;
      const ratio=RICE_SERVING_G/template.weight_g;
      rice.weight_g=RICE_SERVING_G;
      for(const field of NUTRIENTS) rice.contrib[field]=template.contrib[field]*ratio;
      rice.weight_note=NOTE;
      row.itemDetails.push(rice);
      row.components.push('쌀밥');
      row.weight=round(row.weight+RICE_SERVING_G,1);
      const totals=Object.fromEntries(NUTRIENTS.map(field=>[field,row[field]+rice.contrib[field]]));
      for(const field of NUTRIENTS) row[field]=round(totals[field],['fe','satFat'].includes(field)?2:1);
      row.nrf=nrf(totals);
      row.matchedDb.foodDb.push('쌀밥');
      if(rice.missing.length) (row.missingFields??=[]).push('쌀밥: '+rice.missing.join(','));
      row.qualityFlags=(row.qualityFlags||[]).filter(flag=>flag!=='RICE_PHOTO_MISSING_REVIEW');
      row.qualityFlags.push(RULE_FLAG);
      for(const eu of [row.exchangeUnits,entry.exchangeUnits]){
        if(!eu) continue;
        eu.grain=round(eu.grain+RICE_GRAIN,2);
        (eu.matchedDb.menugen??=[]).push('쌀밥');
        (eu.recipeNotes??=[]).push(NOTE);
      }
      added.push(JSON.parse(key(row)));
    }
    return added;
  }
  const api={apply};
  if(typeof module!=='undefined'&&module.exports) module.exports=api; else root.InstantRice=api;
})(globalThis);
