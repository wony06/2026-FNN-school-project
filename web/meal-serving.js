(function(root){
  'use strict';
  const normalize=value=>String(value??'').normalize('NFKC').toLowerCase().replace(/\s+/g,'');
  const includes=(name,terms)=>terms.some(term=>name.includes(term));
  function reference(food){
    let basis=String(food?.basis??'').normalize('NFKC').trim().replace(/^1\s*회(?:\s*제공량)?\s*:?\s*/u,'');
    if(basis.startsWith('(')&&basis.endsWith(')'))basis=basis.slice(1,-1).trim();
    const match=/^(\d+(?:\.\d+)?)\s*(g|ml)$/i.exec(basis);
    return match&&Number(match[1])>0 ? {amount:Number(match[1]),unit:match[2].toLowerCase()==='g'?'g':'mL'} : null;
  }
  function classify(food){
    if(!food)return null;
    const name=normalize(food.portionName||food.name),type=normalize(food.foodType);
    if(food.kind==='ingredient'||String(food.id??'').startsWith('ingredient:'))return null;
    if((food.kind==='processed'||String(food.id??'').startsWith('processed:'))&&['숙면','건면','생면','유탕면','유탕면류'].includes(type))return null;
    if(includes(name,['분말','농축','원액','희석용','건면','생면','파스타면','스파게티면','부침가루','튀김가루']))return null;
    if(name.endsWith('사리'))return 'extra_noodles';
    if(includes(name,['볶음밥']))return 'fried_rice';
    if(includes(name,['덮밥','비빔밥','짜장밥','자장밥','하이라이스','카레라이스','짬뽕밥','오므라이스','알밥','필라프'])||/(부타동|규동|소보로동|가츠동|가츠돈|돈부리)$/.test(name))return 'rice_bowl';
    if(/^(쌀밥|공기밥|백미밥|현미밥|흑미밥|잡곡밥|보리밥|기장밥|귀리밥|밥)$/.test(name))return 'rice';
    const noodle=includes(name,['국수','우동','라면','라멘','짬뽕','자장면','짜장면','냉면','쫄면','수제비','우육면']);
    if(includes(name,['미니','꼬마'])&&noodle)return 'mini_noodles';
    if(includes(name,['파스타','스파게티']))return 'pasta';
    if(includes(name,['찌개','전골','갈비찜','찜닭'])||name.endsWith('찜'))return 'stew';
    if(type==='국및탕류'||(/(국|국물|매운탕|곰탕|설렁탕|삼계탕|감자탕|갈비탕|추어탕|육개장|해장국|어묵탕)$/.test(name)&&!name.includes('탕수육')))return 'soup';
    if(noodle)return 'noodles';
    if(name==='잡채'||(name.endsWith('잡채')&&!name.includes('고추잡채')))return 'japchae';
    if(includes(name,['소스','드레싱','양념장','파우치'])||/^(간장|고추장|된장|쌈장|초간장|굴소스)$/.test(name)||type==='장류,양념류')return 'sauce';
    if(includes(name,['샐러드']))return 'salad';
    if(includes(name,['김치','무침','나물','겉절이'])||type==='김치류'||type==='생채·무침류'||type==='나물·숙채류')return 'seasoned_side';
    if(name.includes('구이')&&includes(name,['생선','고등어','삼치','갈치','가자미','조기','꽁치','연어','장어','굴비','임연수']))return 'grilled_fish';
    // Main-protein dishes use 151g per the user's explicit 2026-11-12 choice.
    if(includes(name,['까스','돈가스','치킨가스','함박','스테이크','불고기','제육','닭갈비','수육','보쌈','탕수육','닭강정','치킨너겟']))return 'protein_main';
    if(includes(name,['조림','젓갈'])||type==='조림류'||type==='젓갈류')return 'braised_side';
    if(name.includes('볶음')||type==='볶음류')return 'stir_fry_side';
    if(name.includes('구이')||type==='구이류')return 'grilled_side';
    if((name.endsWith('전')&&!name.endsWith('전골'))||name.includes('부침')||type==='전·적및부침류')return 'pancake';
    if(includes(name,['장아찌','단무지','피클','동그랑땡'])||['반찬','튀김류','어패류·해조류'].includes(type))return 'side_fallback';
    return null;
  }
  function lookup(food,table){
    const basis=reference(food),category=classify(food);
    if(!basis)return {state:'unknown_basis'};
    if(category==='extra_noodles')return {state:'extra_noodles',unit:basis.unit};
    if(!table)return {state:'loading'};
    const rule=table.categories?.[category];
    if(!rule)return {state:'missing',unit:basis.unit};
    // Japchae has a separate mL rule; grams follow the ordinary side fallback.
    const selected=category==='japchae'&&basis.unit==='g'?table.categories.side_fallback:rule;
    const amount=selected[basis.unit];
    if(!Number.isFinite(amount)||amount<=0)return {state:'unit_unavailable',category,label:selected.label,unit:basis.unit};
    return {state:'available',amount,unit:basis.unit,category:category==='japchae'&&basis.unit==='g'?'side_fallback':category,
      label:selected.label,source:basis.unit==='g'?selected.sourceG:selected.sourceML,tableVersion:table.version};
  }
  function sourcePriority(food){
    const kind=food.kind||String(food.id??'').split(':')[0],category=classify(food),basis=reference(food);
    const volume=['rice','fried_rice','rice_bowl','noodles','mini_noodles','pasta','soup','stew','sauce'].includes(category);
    const origin=normalize(food.detail);
    if(kind==='recipe')return 20;
    if(kind==='processed')return 30;
    if(kind==='ingredient')return 40;
    if(kind!=='cooked')return 90;
    if(!volume){
      if(basis?.unit==='g'&&origin==='외식(분석함량)')return 0;
      if(basis?.unit==='g'&&origin==='가정식(분석함량)')return 1;
      return 50; // Other schools' mL side dishes must not displace the g-first cascade.
    }
    if(origin.startsWith('산업체급식'))return 0;
    if(origin==='외식(분석함량)')return 1;
    if(origin.startsWith('외식(프랜차이즈'))return 2;
    if(origin.startsWith('외식(재료량'))return 3;
    if(origin.startsWith('가정식'))return 4;
    return 5;
  }
  function searchQuery(value){
    const parts=String(value).split(/[&*+/,]/).map(s=>s.trim()).filter(Boolean);
    const kept=parts.filter(part=>!normalize(part).endsWith('사리'));
    return kept.length&&kept.length<parts.length?kept.join(' '):String(value);
  }
  const api={normalize,reference,classify,lookup,sourcePriority,searchQuery};
  if(typeof module!=='undefined'&&module.exports)module.exports=api;else root.MealServing=api;
})(globalThis);
