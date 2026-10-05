(function(root){
  function rankVisibleMenus(rows,shop,compareMenus){
    const sorted=rows.filter(row=>shop==='all'||row.shop===shop).slice().sort(compareMenus);
    let prior=null,rank=null;
    return sorted.map((item,index)=>{
      if(item.personal.eligible){
        const tied=prior && prior.personal.finalScore===item.personal.finalScore &&
          prior.personal.passesSelectedDietaryConditions===item.personal.passesSelectedDietaryConditions;
        rank=tied ? rank : index+1;
        prior=item;
      } else rank=null;
      return {item,rank};
    });
  }
  const api={rankVisibleMenus};
  if(typeof module!=='undefined'&&module.exports) module.exports=api; else root.RecommendationView=api;
})(globalThis);
