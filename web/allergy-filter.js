(function(root){
  const key=row=>JSON.stringify([row.date,row.shop,row.category,row.main]);
  function buildIndex(data){
    if(data.schemaVersion!==1 || !Array.isArray(data.meals) || !Array.isArray(data.allergens) || data.allergens.length!==19) throw Error('알레르기 데이터 구조를 확인해주세요.');
    const index=new Map();
    for(const entry of data.meals){
      if(!Array.isArray(entry.key)||entry.key.length!==4)throw Error('알레르기 식단 키 오류');
      const k=JSON.stringify(entry.key);
      if(index.has(k))throw Error('알레르기 식단 키 중복');
      if(entry.state==='choice_withheld' && entry.allergens.length)throw Error('통합 보류 식단의 성분 적용 오류');
      index.set(k,entry);
    }
    return index;
  }
  function assess(row,selected,index){
    const entry=index.get(key(row))??null;
    const reasons=entry?.state==='choice_withheld' ? [] : (entry?.allergens??[]).filter(a=>selected.has(a.code));
    return {excluded:reasons.length>0,reasons,entry,
      state:entry?.state??'missing_estimate',requiresIngredientCheck:true};
  }
  function partition(rows,codes,index){
    const selected=new Set(codes.map(Number));
    if([...selected].some(n=>!Number.isInteger(n)||n<1||n>19))throw Error('알레르기 선택값 오류');
    // No selection returns the exact existing rows to preserve all scoring behavior.
    if(!selected.size)return {kept:rows,excluded:[]};
    const kept=[],excluded=[];
    for(const row of rows){
      const assessment=assess(row,selected,index);
      const item={...row,allergyAssessment:assessment};
      (assessment.excluded?excluded:kept).push(item);
    }
    return {kept,excluded};
  }
  const api={key,buildIndex,assess,partition};
  if(typeof module!=='undefined'&&module.exports)module.exports=api;else root.AllergyFilter=api;
})(globalThis);
