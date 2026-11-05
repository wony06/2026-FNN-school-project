(function(root){
  const Score=typeof module!=='undefined'&&module.exports ? require('./personal-score.js') : root.PersonalScore;
  function rankVisibleMenus(rows,shop,compareMenus){
    const sorted=rows.filter(row=>shop==='all'||row.shop===shop).slice().sort(compareMenus);
    let anchor=null,rank=null;
    return sorted.map((item,index)=>{
      if(item.recommendation.eligible){
        const tied=anchor && Score.sameRankMetric(anchor,item);
        rank=tied ? rank : index+1;
        // Compare every member to the group anchor; do not chain approximate ties.
        if(!tied) anchor=item;
      } else rank=null;
      return {item,rank};
    });
  }
  const api={rankVisibleMenus};
  if(typeof module!=='undefined'&&module.exports) module.exports=api; else root.RecommendationView=api;
})(globalThis);
