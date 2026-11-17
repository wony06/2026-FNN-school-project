(function(root){
  'use strict';
  const FIELDS=[['kcal','열량','kcal'],['carb','탄수화물','g'],['protein','단백질','g'],['fat','지방','g']];
  // Existing display-name corrections from pipeline/restore_menu_names.py only.
  const ALIASES={'주먹밥_참치':'참치주먹밥','황태구이_양념':'황태무침'};
  const canonical=name=>ALIASES[name]??name;
  const escape=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  function get(item,index){
    const names=item?.components??[],name=names[index];
    if(typeof name!=='string')return null;
    const label=canonical(name),occurrences=names.filter(n=>canonical(n)===label).length;
    const occurrence=names.slice(0,index).filter(n=>canonical(n)===label).length;
    const matches=(item.itemDetails??[]).filter(d=>canonical(d.display)===label||canonical(d.calculationName)===label);
    const selected=occurrences===1 ? matches : matches.length===occurrences ? [matches[occurrence]] : [];
    const values=Object.fromEntries(FIELDS.map(([key])=>{
      const known=selected.length>0&&selected.every(d=>d.matched!==false&&!(d.missing??[]).includes(key)&&Number.isFinite(d.contrib?.[key])&&d.contrib[key]>=0);
      return [key,known?selected.reduce((sum,d)=>sum+d.contrib[key],0):null];
    }));
    return {name,values,detailCount:selected.length,partial:Object.values(values).some(v=>v===null)};
  }
  function render(item){
    const names=item?.components??[];
    if(!names.length)return '';
    const buttons=names.map((name,i)=>`<button type="button" class="tag component-chip" data-component-index="${i}" aria-expanded="false" aria-controls="sheet-component-values">${escape(name)}</button>`).join('');
    return `<section class="component-nutrition" data-component-nutrition><div class="section-title">구성요소</div><div class="taglist component-buttons">${buttons}</div><div id="sheet-component-values" class="component-values" role="region" aria-label="구성요소별 영양정보" aria-live="polite" hidden></div></section>`;
  }
  function valuesHtml(component){
    const short={carb:'탄',protein:'단',fat:'지'};
    const values=FIELDS.map(([key,label,unit])=>`<div><dt${key==='kcal'?' class="sr-only"':''} aria-label="${label}">${short[key]??label}</dt><dd>${component.values[key]===null?'미확인':'<strong>'+component.values[key].toFixed(1)+'</strong> '+unit}</dd></div>`).join('');
    return `<dl class="component-values-inline">${values}</dl>`;
  }
  function mount(panel,item){
    const section=panel.querySelector('[data-component-nutrition]');
    if(!section)return;
    const values=section.querySelector('.component-values');
    section.addEventListener('click',event=>{
      const button=event.target.closest('button[data-component-index]');
      if(!button||!section.contains(button))return;
      const close=button.getAttribute('aria-expanded')==='true';
      for(const other of section.querySelectorAll('[data-component-index]')){
        const active=!close&&other===button;
        other.setAttribute('aria-expanded',String(active));other.classList.toggle('is-active',active);
      }
      const component=get(item,Number(button.dataset.componentIndex));
      values.hidden=close||!component;
      values.setAttribute('aria-label',component?`${component.name} 영양정보`:'구성요소별 영양정보');
      values.innerHTML=values.hidden?'':valuesHtml(component);
    });
  }
  const api={get,render,mount};
  if(typeof module!=='undefined'&&module.exports)module.exports=api;else root.ComponentNutrition=api;
})(globalThis);
