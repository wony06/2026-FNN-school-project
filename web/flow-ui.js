(function(root){
  function mount({form,validateGoal,onLeave=()=>{}}){
    const pages=[...document.querySelectorAll('[data-step]')],status=document.getElementById('flowStatus');
    const submit=document.getElementById('personalSubmit');
    let current=0,ready=false,hasResults=false,restoring=false;
    form.before(status);form.noValidate=true;
    function clearError(){status.hidden=true;status.textContent='';document.getElementById('guideResumeStatus').hidden=true;}
    function show(step,historyMode='push'){
      if(!Number.isInteger(step)||step<0||step>4)return;
      onLeave();current=step;
      document.getElementById('resultSettingsMenu').open=false;
      pages.forEach(p=>p.hidden=Number(p.dataset.step)!==step);
      form.hidden=step===0||step===4;
      document.body.dataset.flowStep=String(step);
      document.getElementById('flowStepper').hidden=step===0;
      document.querySelectorAll('[data-progress-step]').forEach(item=>{const number=Number(item.dataset.progressStep);item.dataset.state=number===step?'current':number<step?'done':'pending';if(number===step)item.setAttribute('aria-current','step');else item.removeAttribute('aria-current');});
      document.getElementById('flowProgress').textContent=step===0?'나에게 맞는 학식 찾기':`${step} / 4 · ${['','기본 정보','알레르기 설정','영양 목표','개인 맞춤 서비스'][step]}`;
      const panel=document.getElementById('allergyPanel');panel.hidden=true;document.getElementById('allergyToggle').setAttribute('aria-expanded','false');
      if(historyMode!=='none'){
        const url=new URL(location.href);url.hash=`step=${step}`;
        if(historyMode==='replace'||url.href!==location.href)history[historyMode==='replace'?'replaceState':'pushState']({guideStep:step},'',url);
      }
      const headings=document.querySelectorAll(`[data-step="${step}"] :is(h1,h2)[tabindex="-1"]`);
      const heading=Array.from(headings).find(node=>!node.closest('[hidden]'));
      heading?.focus({preventScroll:true});window.scrollTo({top:0,behavior:'auto'});
    }
    function showError(message,step){
      if(step!==undefined)show(step,restoring?'replace':'push');
      status.textContent=message;status.hidden=false;
    }
    function validateSection(step){
      const section=document.querySelector(`[data-step="${step}"]`);
      for(const control of section.querySelectorAll('input,select')){
        if(control.disabled||control.checkValidity())continue;
        show(step,restoring?'replace':'push');control.reportValidity();return false;
      }
      return true;
    }
    function validateSettings(){
      if(!ready){showError('메뉴 자료를 불러오는 중입니다. 잠시 후 다시 시도해주세요.');return false;}
      if(!validateSection(3))return false;
      try{validateGoal();return true;}
      catch(error){showError(error.message,3);return false;}
    }
    function validateForResults(){clearError();return validateSection(1)&&validateSettings();}
    function next(){
      clearError();
      if(current===0)show(1);
      else if(current===1&&validateSection(1))show(2);
      else if(current===2)show(3);
      else if(current===3&&ready)form.requestSubmit(submit);
    }
    function updateAllergyButton(){document.getElementById('allergyNext').textContent=(root.AllergyUI?.selectedCodes().length??0)>0?'다음':'건너뛰기';}
    function setReady(value){
      ready=value;submit.disabled=!value;document.querySelector('[data-flow-next="3"]').disabled=!value;
      updateAllergyButton();updateResumeButton();
    }
    function showResults(context){
      clearError();hasResults=true;
      const field=name=>form.elements.namedItem(name).value;
      const choice=name=>form.querySelector(`[name="${name}"]:checked`)?.closest('label')?.textContent.trim()??'';
      const allergies=[...document.querySelectorAll('#allergyOptions input:checked')].map(input=>input.closest('label').textContent.trim()).join(', ');
      document.getElementById('profileSummary').textContent=`${field('sex')==='male'?'남성':'여성'} · 만 ${field('age')}세 · ${field('heightCm')} cm · ${field('weightKg')} kg · ${choice('activity')} · 하루 ${context.mealCount}끼 · ${choice('goal')}${allergies?' · 선택 알레르기: '+allergies:' · 알레르기 선택 안 함'}`;
      const selectedAllergies=Array.from(document.querySelectorAll('#allergyOptions input:checked'),input=>
        input.closest('label').textContent.trim().replace(/^\d+[.\s]*/,''));
      const allergyTag=selectedAllergies.length
        ? '알레르기 '+selectedAllergies.slice(0,2).join('·')+(selectedAllergies.length>2 ? ` 외 ${selectedAllergies.length-2}종` : '')
        : '알레르기 미선택';
      const brief=document.getElementById('resultSettingsBrief');
      brief.replaceChildren();
      const tagIcons=['leaf','utensils','allergy'];
      for(const [index,text] of [choice('goal'),`하루 ${context.mealCount}끼`,allergyTag].entries()){
        const tag=document.createElement('span');
        tag.className='result-setting-tag';
        tag.setAttribute('role','listitem');
        const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');
        svg.setAttribute('class','result-icon');
        svg.setAttribute('viewBox','0 0 24 24');
        svg.setAttribute('aria-hidden','true');
        const use=document.createElementNS('http://www.w3.org/2000/svg','use');
        use.setAttribute('href',`#result-icon-${tagIcons[index]}`);
        svg.appendChild(use);
        tag.append(svg,document.createTextNode(text));
        brief.appendChild(tag);
      }
      const energy=document.getElementById('resultEer'),energyLabel=document.createElement('span'),energyValue=document.createElement('strong'),energyUnit=document.createElement('span');
      energyLabel.className='energy-label';energyLabel.textContent='하루 필요 에너지(EER)';energyValue.className='energy-number';energyValue.textContent=Number(context.eer.toFixed(0)).toLocaleString('ko-KR');energyUnit.className='energy-unit';energyUnit.textContent=' kcal';energy.replaceChildren(energyLabel,energyValue,energyUnit);
      const target=document.getElementById('resultEnergyTarget');target.hidden=context.goal!=='weight_loss';
      target.textContent=context.goal==='weight_loss'?`감량 하루 목표 ${context.adjustedEer.toFixed(1)} kcal`:'';
      const energyDetails=document.getElementById('resultEnergyDetails');
      energyDetails.hidden=context.goal!=='weight_loss';
      energyDetails.textContent=context.goal==='weight_loss'?`하루 목표 ${context.adjustedEer.toFixed(1)} kcal · 하루 적자 ${context.deficit.toFixed(1)} kcal · 한 끼 열량 상한 ${context.mealEnergyLimit.toFixed(1)} kcal`:'';
      show(4,restoring?'none':'push');
      requestAnimationFrame(()=>root.dispatchEvent(new Event('resize')));
    }
    const settingsMenu=document.getElementById('resultSettingsMenu');
    document.addEventListener('pointerdown',event=>{
      if(settingsMenu.open&&!settingsMenu.contains(event.target)) settingsMenu.open=false;
    });
    settingsMenu.addEventListener('keydown',event=>{
      if(event.key!=='Escape') return;
      settingsMenu.open=false;
      settingsMenu.querySelector('summary').focus();
    });
    function updateResumeButton(){
      const button=document.getElementById('guideResume');
      const saved=root.ProfileStorage.getSavedProfile();
      button.hidden=false;button.disabled=!ready;
      button.textContent='저장된 정보로 바로보기';
      if(saved)document.getElementById('guideResumeStatus').hidden=true;
    }
    document.getElementById('guideResume').addEventListener('click',()=>{
      clearError();
      const saved=root.ProfileStorage.getSavedProfile();
      if(!saved){document.getElementById('guideResumeStatus').hidden=false;return;}
      const step=root.ProfileStorage.resumeStep(saved);
      if(step!==4){show(step);return;}
      if(!ready)return;
      restoring=true;try{form.requestSubmit(submit);}finally{restoring=false;}
    });
    root.addEventListener('hyu-profile-storage-change',updateResumeButton);
    document.getElementById('guideStart').addEventListener('click',next);
    document.getElementById('guideHome').addEventListener('click',event=>{event.preventDefault();clearError();show(0);});
    document.querySelectorAll('[data-flow-next]').forEach(button=>button.addEventListener('click',next));
    document.querySelectorAll('[data-flow-back]').forEach(button=>button.addEventListener('click',()=>{clearError();show(Math.max(0,current-1));}));
    document.querySelectorAll('[data-edit-step]').forEach(button=>button.addEventListener('click',()=>{clearError();show(Number(button.dataset.editStep));}));
    root.addEventListener('popstate',event=>{
      clearError();const step=event.state?.guideStep??0;
      if(step===4&&hasResults){restoring=true;try{form.requestSubmit(submit);}finally{restoring=false;}return;}
      show(step===4?0:step,'none');
    });
    setReady(false);show(0,'replace');
    return {get step(){return current;},get restoringResults(){return restoring;},next,validateForResults,showError,showResults,setReady,updateAllergyButton};
  }
  root.GuideFlow={mount};
})(globalThis);

// Independent help dialog; does not read or update recommendation inputs.
(function(){
  const trigger=document.getElementById('goalDifferenceTrigger');
  const dialog=document.getElementById('goalDifferenceDialog');
  const close=document.getElementById('goalDifferenceClose');
  if(!trigger||!dialog||!close)return;
  trigger.addEventListener('click',()=>{if(dialog.open)return;dialog.showModal();document.body.classList.add('goal-help-open');});
  function restoreFocus(){if(dialog.open)return;document.body.classList.remove('goal-help-open');if(trigger.getClientRects().length)trigger.focus({preventScroll:true});}
  function closeDialog(){dialog.close();restoreFocus();}
  close.addEventListener('click',closeDialog);
  dialog.addEventListener('cancel',event=>{event.preventDefault();closeDialog();});
  dialog.addEventListener('click',event=>{
    if(event.target!==dialog)return;
    const rect=dialog.getBoundingClientRect();
    if(event.clientX<rect.left||event.clientX>rect.right||event.clientY<rect.top||event.clientY>rect.bottom)closeDialog();
  });
  dialog.addEventListener('close',restoreFocus);
})();
