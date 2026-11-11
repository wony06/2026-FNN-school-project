const test=require('node:test'),assert=require('node:assert/strict');
const Store=require('./profile-storage.js');
const profile={sex:'female',age:'22',heightCm:'165',weightKg:'60',activity:'1',mealCount:'3',goal:'weight_loss',monthlyLossKg:'1.5',allergies:[2,9]};
function memory(){const items=new Map();return {items,getItem:k=>items.get(k)??null,setItem:(k,v)=>items.set(k,v),removeItem:k=>items.delete(k)};}
test('명시 동의가 있을 때만 정해진 정보와 동의를 저장한다',()=>{
  const storage=memory();
  Store.writeSaved(storage,profile,false);assert.equal(storage.getItem(Store.KEY),null);
  Store.writeSaved(storage,{...profile,unrelated:'not stored'},true);
  assert.deepEqual(Store.readSaved(storage),profile);
  assert(!storage.getItem(Store.KEY).includes('not stored'));
});
test('동의 해제는 이 서비스 정보만 삭제한다',()=>{
  const storage=memory();storage.setItem('other-app','retain');
  Store.writeSaved(storage,profile,true);Store.writeSaved(storage,profile,false);
  assert.equal(storage.getItem(Store.KEY),null);assert.equal(storage.getItem('other-app'),'retain');
});
test('손상된 정보·동의 없는 기록·잘못된 코드와 목표를 복원하지 않는다',()=>{
  const storage=memory();storage.setItem(Store.KEY,'bad json');assert.equal(Store.readSaved(storage),null);
  storage.setItem(Store.KEY,JSON.stringify({version:1,consent:false,profile}));assert.equal(Store.readSaved(storage),null);
  assert.equal(Store.cleanProfile({...profile,allergies:[0,20]}),null);
  assert.equal(Store.cleanProfile({...profile,goal:'arbitrary'}),null);
  assert.equal(Store.cleanProfile({...profile,sex:'arbitrary'}),null);
  assert.deepEqual(Store.cleanProfile({...profile,allergies:[9,2,9]}).allergies,[2,9]);
});

test('기존 v1 저장정보는 변경 없이 바로가기 가능하며 미선택 알레르기도 완료다',()=>{
 const storage=memory();Store.writeSaved(storage,{...profile,allergies:[]},true);
 const raw=storage.getItem(Store.KEY);assert.equal(Store.resumeStep(Store.readSaved(storage)),4);assert.equal(storage.getItem(Store.KEY),raw);
});
test('부분 저장정보를 보존하고 처음 비어 있는 단계로 연결한다',()=>{
 const storage=memory();
 for(const [missing,step] of [['age',1],['activity',1],['allergies',2],['goal',3]]){
  const partial={...profile};delete partial[missing];Store.writeSaved(storage,partial,true);
  const restored=Store.readSaved(storage);assert(restored);assert.equal(restored.weightKg,'60');assert.equal(Store.resumeStep(restored),step);assert(!Object.hasOwn(restored,missing));
 }
 assert.equal(Store.resumeStep({...profile,age:'19'}),1);
 assert.equal(Store.resumeStep({...profile,monthlyLossKg:'-1'}),3);
 assert.equal(Store.resumeStep({...profile,monthlyLossKg:''}),4);
});
