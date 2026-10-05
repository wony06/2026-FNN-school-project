/* Presentation scoring only. Never recompute or overwrite the stored nrf. */
(function(root) {
  const SHOPS = new Set(['105', '401', '204']);
  function scoreMenus(rows, fixedReference) {
    const eligible = row => SHOPS.has(row.shop) &&
      Array.isArray(row.unmatched) && row.unmatched.length === 0 &&
      Number.isFinite(row.nrf);
    if(!Array.isArray(fixedReference) || !fixedReference.length || !fixedReference.every(Number.isFinite))
      throw new Error('고정 NRF 기준분포를 불러오지 못했습니다');
    const reference = [...fixedReference].sort((a,b) => a-b);
    function upperBound(value) {
      let lo=0, hi=reference.length;
      while(lo<hi) {
        const mid=(lo+hi)>>>1;
        if(reference[mid]<=value) lo=mid+1; else hi=mid;
      }
      return lo;
    }
    const scored=rows.map(row => {
      const ok=eligible(row);
      const percentile=ok ? upperBound(row.nrf)/reference.length*100 : null;
      return {...row, assessment:{eligible:ok, referenceSize:reference.length,
        percentile, nrfPoints:ok ? percentile*0.25 : null,
        eerPoints:null, totalPoints:null, rank:null,
        exclusionReason:ok ? null : (row.unmatched?.length ? '미매칭 항목 있음' : '평가 데이터 확인 필요')}};
    });
    const groups=new Map();
    scored.filter(row=>row.assessment.eligible).forEach(row=>{
      const key=row.date;
      if(!groups.has(key)) groups.set(key,[]);
      groups.get(key).push(row);
    });
    for(const group of groups.values()) {
      group.sort(compareMenus);
      group.forEach((row,i)=>{
        row.assessment.rank=i && row.assessment.nrfPoints===group[i-1].assessment.nrfPoints
          ? group[i-1].assessment.rank : i+1;
      });
    }
    return scored;
  }
  function compareMenus(a,b) {
    return Number(b.assessment.eligible)-Number(a.assessment.eligible) ||
      (b.assessment.nrfPoints??0)-(a.assessment.nrfPoints??0) ||
      a.category.localeCompare(b.category,'ko');
  }
  const api={scoreMenus,compareMenus};
  if(typeof module!=='undefined' && module.exports) module.exports=api;
  else root.NrfRanking=api;
})(globalThis);
