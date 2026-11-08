(function(root){
  let data=null,selected=new Set(),notifyChange=()=>{};
  const esc=v=>String(v).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;');
  function selectedCodes(){return [...selected].sort((a,b)=>a-b);}
  function name(code){return data?.allergens.find(a=>a.code===code)?.name??String(code);}
  function setSelectedCodes(codes,notify=true){
    selected=new Set(codes.filter(n=>Number.isInteger(n)&&n>=1&&n<=19));
    document.querySelectorAll('#allergyOptions input').forEach(input=>input.checked=selected.has(Number(input.value)));
    const button=document.getElementById('allergyToggle'),names=selectedCodes().map(name);
    button.textContent=names.length ? `${names.slice(0,2).join(', ')}${names.length>2?` 외 ${names.length-2}개`:''} (${names.length}개 선택)` : '알레르기 유발 식품 선택';
    button.title=names.join(', ');
    if(notify)notifyChange();
  }
  function mount(value,onChange){
    data=value;notifyChange=onChange;
    const button=document.getElementById('allergyToggle'),panel=document.getElementById('allergyPanel');
    if(!data){button.disabled=true;document.getElementById('allergyLoadStatus').textContent='알레르기 추정 자료를 불러오지 못했습니다. 선택 기능을 사용할 수 없습니다.';return;}
    button.disabled=false;
    const list=document.getElementById('allergyOptions');list.replaceChildren();
    const setOpen=open=>{panel.hidden=!open;button.setAttribute('aria-expanded',String(open));};
    const update=()=>{
      const names=selectedCodes().map(name);
      button.textContent=names.length ? `${names.slice(0,2).join(', ')}${names.length>2?` 외 ${names.length-2}개`:''} (${names.length}개 선택)` : '알레르기 유발 식품 선택';
      button.title=names.join(', ');onChange();
    };
    for(const allergen of data.allergens){
      const label=document.createElement('label');label.className='allergy-option';
      const input=document.createElement('input');input.type='checkbox';input.name='allergy';input.value=allergen.code;
      input.addEventListener('change',()=>{if(input.checked)selected.add(allergen.code);else selected.delete(allergen.code);update();});
      const span=document.createElement('span');span.textContent=`${allergen.code}. ${allergen.name}`;
      label.append(input,span);list.append(label);
    }
    button.onclick=()=>setOpen(panel.hidden);
    document.getElementById('allergyDone').onclick=()=>{setOpen(false);button.focus();};
    document.getElementById('allergyClear').onclick=()=>{
      selected.clear();list.querySelectorAll('input').forEach(input=>input.checked=false);update();
    };
    document.addEventListener('click',e=>{if(!document.getElementById('allergySelect').contains(e.target))setOpen(false);});
    document.getElementById('allergySelect').addEventListener('keydown',e=>{
      if(e.key==='Escape'){e.stopPropagation();setOpen(false);button.focus();}
    });
  }
  function stateText(assessment){
    if(assessment.state==='choice_withheld')return '원재료 확인 필요 · 추정 통합 보류';
    if(assessment.state==='missing_estimate')return '원재료 확인 필요 · 추정 자료 미연결';
    return '원재료 확인 필요';
  }
  function exclusionLabel(assessment){return `${assessment.reasons.map(r=>name(r.code)).join('·')} 알레르기 제외`;}
  function detailsHtml(assessment){
    if(!assessment)return '';
    const held=[...new Set((assessment.entry?.suppressed??[]).filter(e=>e.policy==='reviewed-reference-hold-v2').map(e=>name(e.code)))];
    const note=held.length ? ` 자동 적용 보류: ${held.join('·')} — 원재료 확인 필요.` : '';
    return `<p class="allergy-detail">${esc(stateText(assessment))}.${esc(note)} 실제 원재료·교차접촉 여부는 식당에 확인해 주세요.</p>`;
  }
  function heldInfoHtml(assessment){
    const held=[...new Set((assessment?.entry?.suppressed??[]).filter(e=>e.policy==='reviewed-reference-hold-v2').map(e=>name(e.code)))];
    return held.length ? `<p class="allergy-detail">${esc(held.join('·'))}: 자동 적용 보류 · 원재료 확인 필요</p>` : '';
  }
  function renderSummary(excluded,remaining,total){
    const panel=document.getElementById('allergyResult');panel.hidden=!selected.size;
    if(!selected.size){panel.replaceChildren();return;}
    panel.innerHTML=`<p>전체 ${total}개 · 추천 검토 ${remaining}개 · 알레르기 제외 ${excluded.length}개</p>
      <p>${remaining?'남아 있는 메뉴도 원재료 확인이 필요하며, 선택한 영양 기준으로 정렬됩니다.':'선택한 성분의 포함 가능 근거로 모든 메뉴가 제외됐습니다.'}</p>`;
  }
  root.AllergyUI={mount,selectedCodes,setSelectedCodes,detailsHtml,heldInfoHtml,stateText,exclusionLabel,renderSummary};
})(globalThis);
