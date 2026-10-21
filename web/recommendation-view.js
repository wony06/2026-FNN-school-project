(function(root){
  function rankVisibleMenus(rows,shop,compareMenus){
    const sorted=rows.filter(row=>shop==='all'||row.shop===shop).slice().sort(compareMenus);
    let prior=null,rank=null;
    return sorted.map((item,index)=>{
      if(item.recommendation.eligible){
        const tied=prior && prior.recommendation.metric===item.recommendation.metric;
        rank=tied ? rank : index+1;
        prior=item;
      } else rank=null;
      return {item,rank};
    });
  }
  const api={rankVisibleMenus};
  if(typeof module!=='undefined'&&module.exports) module.exports=api; else root.RecommendationView=api;
})(globalThis);
