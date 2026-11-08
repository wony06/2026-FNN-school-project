(function(root){
  function rankVisibleMenus(rows,shop,compareMenus){
    const sorted=rows.filter(row=>shop==='all'||row.shop===shop).slice().sort(compareMenus);
    let prior=null,rank=null;
    return sorted.map((item,index)=>{
      if(item.recommendation.eligible){
        const pm=prior?.recommendation;
        const tied=pm && pm.metric===item.recommendation.metric && (pm.distance??null)===(item.recommendation.distance??null);
        rank=tied ? rank : index+1;
        prior=item;
      } else rank=null;
      return {item,rank};
    });
  }
  const api={rankVisibleMenus};
  if(typeof module!=='undefined'&&module.exports) module.exports=api; else root.RecommendationView=api;
})(globalThis);
