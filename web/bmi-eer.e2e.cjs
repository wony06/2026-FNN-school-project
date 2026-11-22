const {chromium}=require('playwright');
const fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict'),os=require('node:os');
const Score=require('./personal-score.js');
const url=process.env.HYU_TEST_URL||'http://127.0.0.1:8790/';
const out=process.env.HYU_FLOW_OUTPUT||path.join(os.tmpdir(),'hyu-bmi-eer');fs.mkdirSync(out,{recursive:true});
const normalMessage='현재 BMI가 정상범위에 해당하여 체중감량 목표를 이용할 수 없습니다. 다른 영양목표를 선택해 주세요.';
const lowMessage='현재 BMI가 저체중 범위에 해당하여 체중감량 목표를 이용할 수 없습니다. 다른 영양목표를 선택해 주세요.';
const report={checks:[],errors:[],screens:[]};let browser;
const base={sex:'male',age:22,heightCm:200,weightKg:100,activity:1,mealCount:3};
(async()=>{
 browser=await chromium.launch({headless:true,executablePath:process.env.HYU_BROWSER_PATH||'C:/Program Files/Google/Chrome/Application/chrome.exe'});
 for(const [device,width] of [['desktop',1440],['mobile',390]]){
  const context=await browser.newContext({viewport:{width,height:1000}}),page=await context.newPage();
  page.on('pageerror',e=>report.errors.push(e.message));
  await page.clock.install({time:new Date('2026-11-20T03:00:00Z')});
  await page.goto(url+'?date=2026-11-20&v=bmi-eer-test');await page.waitForFunction(()=>!document.querySelector('#personalSubmit').disabled);
  const stage=()=>page.locator('body').getAttribute('data-flow-step');
  const choose=goal=>page.locator(`.goal-option:has([value="${goal}"])`).click();
  async function editBasic(){
   const step=await stage();
   if(step==='0')await page.locator('#guideStart').click();
   else if(step==='4'){
    await page.locator('#resultSettingsMenu > summary').click();await page.locator('[data-edit-step="1"]').click();
   }else{
    if(step==='3')await page.locator('#guideStep3 [data-flow-back]').click();
    if(await stage()==='2')await page.locator('#guideStep2 [data-flow-back]').click();
   }
   assert.equal(await stage(),'1');
  }
  async function goalPage(weight,height=200,sex='male'){
   await editBasic();await page.locator('[name=sex]').selectOption(sex);
   for(const [name,value] of [['age',22],['heightCm',height],['weightKg',weight]])await page.locator(`[name=${name}]`).fill(String(value));
   await page.locator('.activity-option:has([value="1"])').click();
   await page.locator('[data-flow-next="2"]').click();await page.locator('[data-flow-next="3"]').click();
   assert.equal(await stage(),'3');
  }
  for(const [bmi,allowed,height=200,weight=bmi*4] of [[18.49,false],[18.5,false],[22.9,false],[22.9999,false],[23,true],[24.9,true],[25,true],
    [18.5,false,160,47.36],[23,true,160,58.88],[25,true,160,64]]){
   await goalPage(weight,height);assert(!(await page.locator('[name=goal][value=weight_loss]').isDisabled()));
   await choose('weight_loss');
   assert.equal(await page.locator('[name=goal][value=weight_loss]').isChecked(),allowed);
   assert.equal(await page.locator('#weightLossField').isVisible(),allowed);
   if(!allowed){
    assert.equal(await page.locator('#flowStatus').innerText(),bmi<18.5?lowMessage:normalMessage);
    await page.locator('#personalSubmit').click();assert.equal(await stage(),'3');
    await page.evaluate(()=>personalForm.requestSubmit(document.querySelector('#personalSubmit')));assert.equal(await stage(),'3');
   }
   report.checks.push(`${device}: ${height}cm BMI ${bmi} ${allowed?'선택 가능':'클릭 안내·미선택·다음/직접 제출 차단'}`);
  }
  for(const sex of ['male','female']){
   await goalPage(100,200,sex);await choose('lifestyle');await page.locator('#personalSubmit').click();
   assert.equal(await stage(),'4');const actual=await page.evaluate(()=>ACTIVE_CONTEXT),expected=Score.calculateEer({...base,sex});
   assert.equal(actual.eer,expected.eer);assert.equal(actual.eerWeightKg,sex==='male'?91:88);assert.equal(actual.weightKg,100);
   assert((await page.locator('#profileSummary').textContent()).includes('100 kg'));
   await page.locator('#mealDiaryTab').click();
   const target=Number((await page.locator('.meal-energy-goal strong').innerText()).replaceAll(',',''));
   assert(Math.abs(target-expected.eer)<=0.051);await page.locator('#mealRecommendTab').click();
   report.checks.push(`${device}: ${sex} 조정 EER → 추천·오늘의 식단, 실제체중 표시 보존`);
  }
  await goalPage(100);await choose('high_protein');await page.locator('#personalSubmit').click();
  assert.equal((await page.evaluate(()=>ACTIVE_CONTEXT)).proteinThreshold,40);
  assert(!(await page.locator('body').innerText()).includes('조정체중'));
  assert(!(await page.locator('body').innerText()).includes('이상체중'));
  report.checks.push(`${device}: 고단백 실제체중×0.4 유지·추가 BMI/조정체중 UI 없음`);

  await goalPage(100);await choose('weight_loss');await page.locator('[name=monthlyLossKg]').fill('1');await page.locator('#personalSubmit').click();
  assert.equal(await stage(),'4');const loss=await page.evaluate(()=>ACTIVE_CONTEXT);
  assert.equal(loss.deficit,7000/30);await page.locator('#mealDiaryTab').click();
  assert(Math.abs(Number((await page.locator('.meal-energy-goal strong').innerText()).replaceAll(',',''))-loss.adjustedEer)<=0.051);
  await page.locator('#mealRecommendTab').click();
  await editBasic();await page.locator('[name=weightKg]').fill('90');
  assert(!(await page.locator('[name=goal][value=weight_loss]').isChecked()));
  await page.locator('[data-flow-next="2"]').click();await page.locator('[data-flow-next="3"]').click();
  assert.equal(await page.locator('#flowStatus').innerText(),normalMessage);
  await page.evaluate(()=>GUIDE_FLOW.showResults(ACTIVE_CONTEXT));assert.equal(await stage(),'3');
  await page.evaluate(()=>dispatchEvent(new PopStateEvent('popstate',{state:{guideStep:4}})));assert.equal(await stage(),'3');
  for(const goal of ['lifestyle','glycemic','balanced','high_protein','low_sugar','low_sodium']){
   await choose(goal);assert(await page.locator('#flowStatus').isHidden());await page.locator('#personalSubmit').click();assert.equal(await stage(),'4');
   await page.locator('#resultSettingsMenu > summary').click();await page.locator('[data-edit-step="3"]').click();
  }
  report.checks.push(`${device}: 체중 변경 즉시 감량 무효화·화면 함수/히스토리 우회 차단·나머지 6목표 이동`);

  await goalPage(100);await choose('weight_loss');await editBasic();await page.locator('[name=heightCm]').fill('210');
  assert(!(await page.locator('[name=goal][value=weight_loss]').isChecked()));
  await page.locator('[name=heightCm]').fill('200');await page.locator('[data-flow-next="2"]').click();await page.locator('[data-flow-next="3"]').click();
  await choose('weight_loss');assert(await page.locator('[name=goal][value=weight_loss]').isChecked());
  await goalPage(22.9*4);await choose('weight_loss');
  assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
  await page.screenshot({path:path.join(out,`${device}-restricted.png`),fullPage:true});report.screens.push(`${device}-restricted.png`);
  report.checks.push(`${device}: 신장 변경 즉시 재검사·BMI 회복 후 재선택·안내문 줄바꿈`);
  await context.close();
 }
 const context=await browser.newContext(),page=await context.newPage();page.on('pageerror',e=>report.errors.push(e.message));
 await page.goto(url);await page.waitForFunction(()=>!document.querySelector('#personalSubmit').disabled);
 const saved={sex:'male',age:'22',heightCm:'200',weightKg:'80',activity:'1',mealCount:'3',goal:'weight_loss',monthlyLossKg:'1',allergies:[]};
 const record=JSON.stringify({version:1,consent:true,profile:saved});
 await page.evaluate(value=>localStorage.setItem('hyu-menu-guide.profile.v1',value),record);await page.reload();
 await page.waitForFunction(()=>!document.querySelector('#personalSubmit').disabled);
 assert.equal(await page.evaluate(()=>localStorage.getItem('hyu-menu-guide.profile.v1')),record);
 await page.locator('#guideResume').click();assert.equal(await page.locator('body').getAttribute('data-flow-step'),'3');
 assert.equal(await page.locator('#flowStatus').innerText(),normalMessage);
 await page.locator('#personalSubmit').click();assert.equal(await page.locator('body').getAttribute('data-flow-step'),'3');
 await page.locator('.goal-option:has([value=high_protein])').click();await page.locator('#personalSubmit').click();
 assert.equal(await page.locator('body').getAttribute('data-flow-step'),'4');
 const updated=JSON.parse(await page.evaluate(()=>localStorage.getItem('hyu-menu-guide.profile.v1')));
 assert.equal(updated.profile.weightKg,'80');assert.equal(updated.profile.goal,'high_protein');assert(!('eerWeightKg' in updated.profile));
 report.checks.push('저장된 정상체중 감량 목표: 원본 보존→목표 화면 안내→새 목표로 이동, 실제체중만 저장');
 await context.close();assert.deepEqual(report.errors,[]);
 fs.writeFileSync(path.join(out,'browser-report.json'),JSON.stringify(report,null,2));console.log(JSON.stringify(report,null,2));
})().catch(error=>{console.error(error);process.exitCode=1;}).finally(async()=>{await browser?.close();});
