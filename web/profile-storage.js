(function(root){
  const KEY='hyu-menu-guide.profile.v1';
  const goals=['lifestyle','weight_loss','glycemic','balanced','high_protein','low_sugar','low_sodium'];
  const fields=['sex','age','heightCm','weightKg','activity','mealCount','goal','monthlyLossKg'];
  let form=null,storage=null,toggle=null,status=null,allergyUI=null;
  function showStatus(message,error=false){status.textContent=message;status.hidden=!error;}
  function cleanProfile(value){
    if(!value||typeof value!=='object')return null;
    const out={};
    for(const name of fields){
      if(typeof value[name]!=='string'||value[name].length>64)return null;
      out[name]=value[name];
    }
    if(!['','male','female'].includes(out.sex)||!['','0','1','2','3'].includes(out.activity)||
       !['2','3'].includes(out.mealCount)||!goals.includes(out.goal))return null;
    if(!Array.isArray(value.allergies)||value.allergies.some(n=>!Number.isInteger(n)||n<1||n>19))return null;
    out.allergies=[...new Set(value.allergies)].sort((a,b)=>a-b);
    return out;
  }
  function readSaved(target){
    const raw=target.getItem(KEY);
    if(!raw)return null;
    try{
      const record=JSON.parse(raw);
      return record.version===1&&record.consent===true ? cleanProfile(record.profile) : null;
    }catch{return null;}
  }
  function writeSaved(target,profile,consent){
    if(!consent){target.removeItem(KEY);return;}
    const clean=cleanProfile(profile);
    if(!clean)throw Error('저장할 입력값을 확인해주세요.');
    target.setItem(KEY,JSON.stringify({version:1,consent:true,profile:clean}));
  }
  function collect(){
    const value={};
    for(const name of fields){
      const inputs=[...form.querySelectorAll(`[name="${name}"]`)];
      value[name]=inputs[0]?.type==='radio' ? inputs.find(input=>input.checked)?.value??'' : inputs[0]?.value??'';
    }
    value.allergies=allergyUI.selectedCodes();
    return value;
  }
  function saveIfEnabled(){
    if(!form||!toggle.checked||!storage)return;
    try{writeSaved(storage,collect(),true);showStatus('입력 정보를 이 브라우저에 저장했어요.');}
    catch{
      toggle.checked=false;
      try{storage.removeItem(KEY);}catch{}
      showStatus('브라우저 설정 또는 저장 공간 때문에 저장하지 못했어요. 저장 기능을 다시 확인해주세요.',true);
    }
  }
  function mount(targetForm,ui,onRestore){
    form=targetForm;allergyUI=ui;
    toggle=document.getElementById('rememberProfile');status=document.getElementById('profileStorageStatus');
    const remove=document.getElementById('deleteProfile');
    try{storage=root.localStorage;storage.getItem(KEY);}
    catch{
      storage=null;toggle.disabled=true;remove.disabled=true;
      showStatus('이 브라우저에서는 정보 저장 기능을 사용할 수 없어요.',true);return;
    }
    const saved=readSaved(storage);
    if(saved){
      for(const name of fields){
        for(const input of form.querySelectorAll(`[name="${name}"]`)){
          if(input.type==='radio')input.checked=input.value===saved[name];else input.value=saved[name];
        }
      }
      ui.setSelectedCodes(saved.allergies,false);
      toggle.checked=true;showStatus('이 브라우저에 저장된 정보를 불러왔어요.');
      onRestore();
    }
    toggle.addEventListener('change',()=>{
      if(toggle.checked)saveIfEnabled();
      else{
        try{storage.removeItem(KEY);showStatus('정보 기억하기를 해제하고 저장된 정보를 삭제했어요.');}
        catch{showStatus('저장된 정보를 삭제하지 못했어요. 브라우저 저장 설정을 확인해주세요.',true);}
      }
    });
    remove.addEventListener('click',()=>{
      try{storage.removeItem(KEY);toggle.checked=false;showStatus('저장된 정보를 삭제했어요. 현재 화면의 입력은 유지됩니다.');}
      catch{showStatus('저장된 정보를 삭제하지 못했어요. 브라우저 저장 설정을 확인해주세요.',true);}
    });
    for(const event of ['input','change'])form.addEventListener(event,e=>{
      if(fields.includes(e.target.name)||e.target.name==='allergy')saveIfEnabled();
    });
  }
  const api={KEY,cleanProfile,readSaved,writeSaved,mount,saveIfEnabled};
  if(typeof module!=='undefined'&&module.exports)module.exports=api;else root.ProfileStorage=api;
})(globalThis);
