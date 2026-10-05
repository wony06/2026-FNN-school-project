(function(root){
  const fields=['grain','meat','veg','fat'];
  const PA={male:[1,1.11,1.25,1.48],female:[1,1.12,1.27,1.45]};
  const key=r=>JSON.stringify([r.date,r.shop,r.category,r.main]);
  function calculateTarget(p,table){
    if(!p || !PA[p.sex] || !Number.isInteger(p.age) || p.age<20 ||
      !Number.isFinite(p.heightCm) || p.heightCm<=0 || !Number.isFinite(p.weightKg) || p.weightKg<=0 ||
      !Number.isInteger(p.activity) || p.activity<0 || p.activity>3) throw Error('성별, 만 20세 이상 나이, 양수 키·체중, 활동수준을 확인해주세요.');
    const h=p.heightCm/100,pa=PA[p.sex][p.activity];
    const eer=p.sex==='male' ? 662-9.53*p.age+pa*(15.91*p.weightKg+539.6*h) :
      354-6.91*p.age+pa*(9.36*p.weightKg+726*h);
    if(!Number.isFinite(eer) || eer<=0) throw Error('계산된 EER이 양수가 아닙니다. 입력을 확인해주세요.');
    const roundedEer=Math.floor((eer+50)/100)*100;
    if(roundedEer<1200 || roundedEer>2800) throw Error(`반올림 EER ${roundedEer}kcal: 현재 식품교환표 적용 범위 밖(1,200~2,800kcal)입니다.`);
    const row=table.dailyExchanges[String(roundedEer)];
    if(!row || row.length!==7 || !row.every(v=>Number.isFinite(v)&&v>=0)) throw Error('해당 열량의 식품교환단위 자료 오류');
    const daily=[row[0],row[1]+row[2],row[3],row[4]];
    if(daily.length!==4 || !daily.every(v=>Number.isFinite(v)&&v>=0) || !daily.some(v=>v>0)) throw Error('목표 교환단위 자료 오류');
    return {eer,roundedEer,pa,dailyTarget:[...daily],mealTarget:daily.map(v=>v/3)};
  }
  function fit(actual,target){
    if(actual.length!==4 || target.length!==4 || ![...actual,...target].every(v=>Number.isFinite(v)&&v>=0)) throw Error('교환단위 자료 오류');
    const denominator=Math.hypot(...target);
    if(!denominator) throw Error('목표 벡터가 0입니다.');
    const distance=Math.hypot(...actual.map((v,i)=>v-target[i]))/denominator;
    return {distance,fit:Math.max(0,100*(1-distance))};
  }
  function scoreMenus(rows,snapshot,target){
    const index=new Map();
    for(const entry of snapshot.entries){
      const k=JSON.stringify(entry.key);
      if(index.has(k)) throw Error('교환단위 식단 키 중복');
      index.set(k,entry);
    }
    const scored=rows.map(row=>{
      const entry=index.get(key(row)), eu=entry?.exchangeUnits;
      const m=eu ? fields.map(f=>eu[f]) : null;
      let reason=!row.assessment.eligible ? '영양성분 미매칭 또는 NRF 평가 불가' :
        !eu ? '교환단위 자료 없음' :
        !Array.isArray(eu.unmatched) || eu.unmatched.length ? '교환단위 미매칭 포함' :
        !m.every(v=>Number.isFinite(v)&&v>=0) ? '필수 교환단위 값 없음' :
        !target ? '개인정보 입력·목표 확인 필요' : null;
      const personal={eligible:!reason,reason,rank:null,actual:m,eer:target?.eer??null,
        roundedEer:target?.roundedEer??null,target:target?.mealTarget??null,fit:null,
        distance:null,personalScore:null,nrfScore:row.assessment.nrfPoints,finalScore:null};
      if(!reason){
        Object.assign(personal,fit(m,target.mealTarget));
        personal.personalScore=personal.fit*.75;
        personal.finalScore=personal.personalScore+personal.nrfScore;
      }
      return {...row,personal,friendExchangeUnits:eu??null};
    });
    const groups=new Map();
    scored.filter(r=>r.personal.eligible).forEach(r=>{
      const k=JSON.stringify([r.date,r.shop]);
      if(!groups.has(k)) groups.set(k,[]);
      groups.get(k).push(r);
    });
    for(const group of groups.values()){
      group.sort(compareMenus);
      group.forEach((r,i)=>r.personal.rank=i && r.personal.finalScore===group[i-1].personal.finalScore ? group[i-1].personal.rank:i+1);
    }
    return scored;
  }
  function compareMenus(a,b){return Number(b.personal.eligible)-Number(a.personal.eligible) || (b.personal.finalScore??0)-(a.personal.finalScore??0) || a.category.localeCompare(b.category,'ko');}
  const api={calculateTarget,fit,scoreMenus,compareMenus};
  if(typeof module!=='undefined'&&module.exports) module.exports=api; else root.PersonalScore=api;
})(globalThis);
