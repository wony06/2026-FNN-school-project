(function(root){
  const fields=['grain','meat','veg','fat'];
  const PA={male:[1,1.11,1.25,1.48],female:[1,1.12,1.27,1.45]};
  const goals=new Set(['lifestyle','weight_loss','glycemic','balanced','high_protein','low_sugar','low_sodium']);
  const exchangeGoals=new Set(['lifestyle','weight_loss','glycemic']);
  const key=r=>JSON.stringify([r.date,r.shop,r.category,r.main]);
  const fmtKcal=n=>String(n).replace(/\B(?=(\d{3})+(?!\d))/g,',');
  function tableBounds(t){
    const ks=Object.keys(t?.dailyExchanges||{}).map(Number).filter(Number.isFinite);
    if(!ks.length) throw Error('식품교환단위 표가 비어 있습니다.');
    return [Math.min(...ks),Math.max(...ks)];
  }

  function calculateEer(p){
    if(!p || !PA[p.sex] || !Number.isInteger(p.age) || p.age<20 ||
      !Number.isFinite(p.heightCm) || p.heightCm<=0 || !Number.isFinite(p.weightKg) || p.weightKg<=0 ||
      !Number.isInteger(p.activity) || p.activity<0 || p.activity>3 ||
      ![2,3].includes(p.mealCount)) throw Error('성별, 만 20세 이상 나이, 양수 키·체중, 활동수준, 하루 2~3끼를 확인해주세요.');
    const h=p.heightCm/100, pa=PA[p.sex][p.activity];
    const eer=p.sex==='male' ? 662-9.53*p.age+pa*(15.91*p.weightKg+539.6*h) :
      354-6.91*p.age+pa*(9.36*p.weightKg+726*h);
    if(!Number.isFinite(eer) || eer<=0) throw Error('계산된 EER이 양수가 아닙니다. 입력을 확인해주세요.');
    return {eer,pa};
  }

  function createContext(p,goal,table,glycemicTable,monthlyLossKg=null){
    if(!goals.has(goal)) throw Error('추천 기준을 선택해주세요.');
    const {eer,pa}=calculateEer(p);
    let deficit=null,adjustedEer=eer,roundedEer=null,dailyTarget=null,mealTarget=null;
    if(goal==='weight_loss'){
      if(monthlyLossKg!==null){
        if(!Number.isFinite(monthlyLossKg) || monthlyLossKg<0) throw Error('한 달 목표 감량 체중은 0 이상의 숫자로 입력해주세요.');
        deficit=Math.min(1000,monthlyLossKg*7000/30);
      } else deficit=750;
      adjustedEer=eer-deficit;
      const [loss_lo,loss_hi]=tableBounds(table);
      if(adjustedEer<loss_lo || adjustedEer>loss_hi) throw Error(`감량 후 하루 목표 ${adjustedEer.toFixed(1)} kcal: 현재 식품교환표 적용 범위 밖(${fmtKcal(loss_lo)}~${fmtKcal(loss_hi)} kcal)입니다. 목표를 검토해주세요.`);
    }
    if(exchangeGoals.has(goal)){
      roundedEer=Math.floor((adjustedEer+50)/100)*100;
      const selectedTable=goal==='glycemic' ? glycemicTable : table;
      const [lo,hi]=tableBounds(selectedTable);
      if(roundedEer<lo || roundedEer>hi) throw Error(`반올림 열량 ${roundedEer} kcal: 현재 ${goal==='glycemic'?'혈당관리용 ':''}식품교환표 적용 범위 밖(${fmtKcal(lo)}~${fmtKcal(hi)} kcal)입니다.`);
      const row=selectedTable?.dailyExchanges?.[String(roundedEer)];
      if(!row) throw Error(`${roundedEer} kcal에 해당하는 ${goal==='glycemic'?'혈당관리용':'일반'} 식품교환단위 표가 없습니다.`);
      if(row.length<(goal==='glycemic'?8:7) || !row.every(v=>Number.isFinite(v)&&v>=0)) throw Error('해당 열량의 식품교환단위 자료 오류');
      dailyTarget=[row[0],row[1]+row[2],row[3],row[4]];
      if(!dailyTarget.some(v=>v>0)) throw Error('목표 교환단위 자료 오류');
      mealTarget=dailyTarget.map(v=>v/p.mealCount);
    }
    return {goal,eer,pa,mealCount:p.mealCount,weightKg:p.weightKg,monthlyLossKg,
      deficit,adjustedEer,roundedEer,dailyTarget,mealTarget,
      mealEnergyLimit:goal==='weight_loss'?adjustedEer/p.mealCount:null,
      proteinThreshold:goal==='high_protein'?p.weightKg*.4:null};
  }

  function calculateDistance(actual,target){
    if(actual.length!==4 || target.length!==4 || ![...actual,...target].every(v=>Number.isFinite(v)&&v>=0)) throw Error('교환단위 자료 오류');
    const denominator=Math.hypot(...target);
    if(!denominator) throw Error('목표 벡터가 0입니다.');
    const distance=Math.hypot(...actual.map((v,i)=>v-target[i]))/denominator;
    return {distance};
  }

  function scoreMenus(rows,snapshot,context){
    const index=new Map();
    for(const entry of snapshot.entries){
      const k=JSON.stringify(entry.key);
      if(index.has(k)) throw Error('교환단위 식단 키 중복');
      index.set(k,entry.exchangeUnits);
    }
    return rows.map(row=>{
      const eu=index.get(key(row))??null;
      const m=eu ? fields.map(f=>eu[f]) : null;
      const goal=context?.goal??null;
      let reason=!context ? '사용자 정보와 추천 기준을 입력해주세요.' :
        !Array.isArray(row.unmatched) || row.unmatched.length ? '영양성분 미매칭 포함' : null;
      if(!reason && exchangeGoals.has(goal)){
        reason=!eu ? '교환단위 자료 없음' :
          !Array.isArray(eu.unmatched) || eu.unmatched.length ? '교환단위 미매칭 포함' :
          !m.every(v=>Number.isFinite(v)&&v>=0) ? '필수 교환단위 값 없음' : null;
        if(!reason && goal==='weight_loss' && (!Number.isFinite(row.kcal) || row.kcal>context.mealEnergyLimit))
          reason=`한 끼 목표 열량 ${context.mealEnergyLimit.toFixed(1)} kcal 초과`;
      }
      if(!reason && goal==='balanced' && !Number.isFinite(row.nrf)) reason='NRF 원점수 없음';
      if(!reason && goal==='high_protein' && (!Number.isFinite(row.protein) || row.protein<context.proteinThreshold))
        reason=`단백질 기준 ${context.proteinThreshold.toFixed(1)} g 미달 또는 자료 없음`;
      if(!reason && goal==='low_sugar' && !Number.isFinite(row.sugar)) reason='총당류 자료 없음';
      if(!reason && goal==='low_sodium' && !Number.isFinite(row.na)) reason='나트륨 자료 없음';
      const recommendation={eligible:!reason,reason,goal,rank:null,metric:null,distance:null,
        actual:m,target:context?.mealTarget??null,eer:context?.eer??null,adjustedEer:context?.adjustedEer??null,
        roundedEer:context?.roundedEer??null,mealCount:context?.mealCount??null,deficit:context?.deficit??null,
        mealEnergyLimit:context?.mealEnergyLimit??null,proteinThreshold:context?.proteinThreshold??null};
      if(!reason){
        if(exchangeGoals.has(goal)){
          const result=calculateDistance(m,context.mealTarget);
          recommendation.distance=result.distance;
          recommendation.metric=result.distance;
        } else recommendation.metric={balanced:row.nrf,high_protein:row.protein,low_sugar:row.sugar,low_sodium:row.na}[goal];
      }
      return {...row,recommendation,friendExchangeUnits:eu};
    });
  }

  function compareMenus(a,b){
    const x=a.recommendation,y=b.recommendation;
    if(x.eligible!==y.eligible) return Number(y.eligible)-Number(x.eligible);
    if(x.eligible){
      const ascending=exchangeGoals.has(x.goal)||x.goal==='low_sugar'||x.goal==='low_sodium';
      const diff=ascending ? x.metric-y.metric : y.metric-x.metric;
      if(diff) return diff;
      if(x.distance!=null && y.distance!=null){const dd=x.distance-y.distance;if(dd)return dd;}
    }
    return a.shop.localeCompare(b.shop) || a.category.localeCompare(b.category,'ko') || a.main.localeCompare(b.main,'ko');
  }
  function sameRankMetric(a,b){
    const x=a.recommendation,y=b.recommendation;
    if(!x.eligible||!y.eligible||x.goal!==y.goal) return false;
    if(!exchangeGoals.has(x.goal)) return x.metric===y.metric;
    if(!Number.isFinite(x.distance)||!Number.isFinite(y.distance)) return false;
    // Eight machine epsilons absorb arithmetic roundoff, never display rounding.
    return Math.abs(x.distance-y.distance)<=8*Number.EPSILON*Math.max(1,Math.abs(x.distance),Math.abs(y.distance));
  }
  const api={calculateEer,createContext,calculateDistance,scoreMenus,compareMenus,sameRankMetric};
  if(typeof module!=='undefined'&&module.exports) module.exports=api; else root.PersonalScore=api;
})(globalThis);
