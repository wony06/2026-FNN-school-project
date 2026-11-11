// Run with NODE_PATH pointing to Playwright and a static server for web/.
const {chromium}=require('playwright');
const assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),os=require('node:os');
const Score=require('./personal-score.js'),View=require('./recommendation-view.js'),Rice=require('./instant-rice.js');
const load=n=>JSON.parse(fs.readFileSync(path.join(__dirname,n),'utf8'));
const output=process.env.HYU_FLOW_OUTPUT||path.join(os.tmpdir(),'hyu-guide-flow');fs.mkdirSync(output,{recursive:true});
const url=process.env.HYU_TEST_URL||'http://127.0.0.1:8790/';
const profile={sex:'male',age:22,heightCm:170,weightKg:65,activity:1,mealCount:3};
const rows=load('site_data.json'),snapshot=load('menu_exchange_snapshot.json');Rice.apply(rows,snapshot);
const normal=load('eer_exchange_targets.json'),glycemic=load('glycemic_exchange_targets.json');
const groups=['lifestyle','weight_loss','glycemic','balanced','high_protein','low_sugar','low_sodium'];
let browser;const checks=[],errors=[];
const note=name=>checks.push(name);
(async()=>{
 const executable=process.env.HYU_BROWSER_PATH||'C:/Program Files/Google/Chrome/Application/chrome.exe';
 browser=await chromium.launch({headless:true,...(fs.existsSync(executable)?{executablePath:executable}:{})});
 const context=await browser.newContext({viewport:{width:1440,height:1000}}),page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));
 const stage=()=>page.locator('body').getAttribute('data-flow-step');
 const shot=name=>page.screenshot({path:path.join(output,name+'.png'),fullPage:true});
 async function submitResult(){
  if(await stage()==='2')await page.locator('[data-flow-next="3"]').click();
  await page.locator('#personalSubmit').click();
 }
 async function resultFor(goal){
  if(await stage()==='4')await editStep(3);
  await page.locator(`[name=goal][value=${goal}]`).check({force:true});
  if(goal==='weight_loss')await page.locator('[name=monthlyLossKg]').fill('');
  await submitResult();assert.equal(await stage(),'4');
 }

  async function editStep(step){
   const button=page.locator(`[data-edit-step="${step}"]`);
   if(!await button.isVisible()) await page.locator('#resultSettingsMenu > summary').click();
   await button.click();
  }
 await page.clock.install({time:new Date('2026-11-04T03:00:00Z')});
 await page.goto(url+'?date=2026-11-04&v=step-flow-test');await page.waitForFunction(()=>!document.querySelector('#personalSubmit').disabled);
 assert.equal(await stage(),'0');assert(await page.locator('#guideStep0 img').isVisible());assert(!(await page.locator('#personalForm').isVisible()));await shot('cover');note('표지 및 기존 마스코트');
 await page.locator('#guideStart').click();assert.equal(await stage(),'1');
 await page.locator('[data-flow-next="2"]').click();assert.equal(await stage(),'1');
 await page.locator('[name=sex]').selectOption('male');
 for(const [n,v] of [['age','19'],['heightCm','170'],['weightKg','65']])await page.locator(`[name=${n}]`).fill(v);
 await page.locator('[name=activity][value="1"]').check({force:true});
 await page.locator('[data-flow-next="2"]').click();assert.equal(await stage(),'1');
 await page.locator('[name=age]').fill('22');assert((await page.locator('#activityDescription').innerText()).includes('통학'));
 assert(!(await page.locator('#resultEer').isVisible()));await page.locator('#eerBasis summary').click();assert((await page.locator('#eerBasis').innerText()).includes('539.6'));await page.locator('#eerBasis summary').click();
 await page.locator('#rememberProfile').check();await shot('basic');note('필수값·20세 검증, 활동 설명, EER 펼쳐보기·결과 전 숨김');
 await page.locator('[data-flow-next="2"]').click();assert.equal(await stage(),'2');
 assert(await page.locator('#allergyStepHeading').isVisible());assert.equal(await page.locator('#allergyNext').innerText(),'건너뛰기');
 await page.locator('#allergyToggle').click();assert.equal(await page.locator('#allergyOptions input').count(),19);
 for(const n of [2,9])await page.locator(`#allergyOptions input[value="${n}"]`).check();
 await page.locator('#allergyDone').click();assert.equal(await page.locator('#allergyNext').innerText(),'다음');await shot('allergy');
 await page.locator('[data-flow-next="3"]').click();assert.equal(await stage(),'3');
 for(const goal of groups){
  await page.locator(`[name=goal][value=${goal}]`).check({force:true});assert.equal(await page.locator('[name=goal]:checked').count(),1);
  assert.equal(await page.locator('#weightLossField').isVisible(),goal==='weight_loss');assert(await page.locator('#goalDescription').isVisible());
 }
 await page.locator('[name=goal][value=weight_loss]').check({force:true});await page.locator('[name=monthlyLossKg]').fill('-1');await submitResult();assert.equal(await stage(),'3');
 await page.locator('[name=goal][value=balanced]').check({force:true});await shot('goals');
 await page.locator('#guideStep3 [data-flow-back]').click();assert.equal(await stage(),'2');assert((await page.locator('#allergyToggle').innerText()).includes('2개 선택'));
 await page.locator('#guideStep2 [data-flow-back]').click();assert.equal(await stage(),'1');assert.equal(await page.locator('[name=heightCm]').inputValue(),'170');
 await page.locator('[data-flow-next="2"]').click();await page.locator('#allergyToggle').click();await page.locator('#allergyClear').click();await page.locator('#allergyDone').click();
 assert.equal(await page.locator('#allergyNext').innerText(),'건너뛰기');await page.locator('[data-flow-next="3"]').click();assert(await page.locator('[name=goal][value=balanced]').isChecked());
 await page.goBack();assert.equal(await stage(),'2');await page.locator('[data-flow-next="3"]').click();
 await submitResult();assert.equal(await stage(),'4');
 note('기본정보 → 알레르기 → 영양목표 순서, 19종 선택, 7목표와 감량 검증, 뒤로가기 입력 유지');
 const date='2026-11-04';const modeChecks=[];
 for(const goal of groups){
  await resultFor(goal);
  const ctx=Score.createContext(profile,goal,normal,glycemic),expected=View.rankVisibleMenus(Score.scoreMenus(rows,snapshot,ctx).filter(r=>r.date===date),'all',Score.compareMenus);
  const actual=await page.evaluate(()=>DATA.filter(r=>r.date===activeDate).map(r=>({key:[r.date,r.shop,r.category,r.main],recommendation:r.recommendation})));
  const expectedByKey=new Map(expected.map(x=>[JSON.stringify([x.item.date,x.item.shop,x.item.category,x.item.main]),x.item.recommendation]));
  for(const a of actual)assert.deepEqual(a.recommendation,expectedByKey.get(JSON.stringify(a.key)));
  assert.deepEqual(await page.locator('.rank-pill').allTextContents(),expected.filter(x=>x.rank!==null).map(x=>`전체 ${x.rank}위`));
  assert(!(await page.locator('#shopGrid').innerText()).includes('목표 식품교환단위와의 거리'));
  assert.equal(await page.locator('#shopGrid .nrf-num').count(),0);assert.equal(await page.locator('#shopGrid .score-details').count(),0);
  assert.equal(await page.locator('.card').count(),6);modeChecks.push(goal);
 }
 note('7모드의 계산값·평가 여부·순위 기존 함수와 완전 일치; 메인 카드 D·NRF 원점수 미노출');
 await resultFor('lifestyle');
 await page.locator('.card-more').first().click();await page.locator('#sheet.open').waitFor();
 assert.equal(await page.locator('#sheetPanel .nutri-table tr').count(),12);
 assert.equal(await page.locator('#sheetPanel .nrf-block').count(),0);
 assert(!(await page.locator('#sheetPanel').innerText()).includes('추천 기준:'));
 assert(!(await page.locator('#sheetPanel').innerText()).includes('목표 식품교환단위와의 거리'));
 const exchange=page.locator('#sheetBody [data-tab=exchange]');if(await exchange.count()){await exchange.click();assert((await page.locator('#sheetBody').innerText()).includes('곡류'));}
 await page.locator('#sheetClose').click();note('상세정보 영양표·교환단위 유지; 상단 추천 설명·NRF 박스 제거');
 const tabs=page.locator('#shopTabs button');await tabs.nth(1).click();assert((await page.locator('.rank-pill').allTextContents()).every(t=>!t.includes('전체')));await tabs.first().click();
 await editStep(1);assert.equal(await page.locator('[name=age]').inputValue(),'22');await page.locator('[name=mealCount][value="2"]').check({force:true});
 await page.locator('[data-flow-next="2"]').click();await page.locator('[data-flow-next="3"]').click();await submitResult();
 const two=await page.evaluate(()=>ACTIVE_CONTEXT);assert.equal(two.mealCount,2);const three=Score.createContext(profile,'lifestyle',normal,glycemic);two.mealTarget.forEach((v,i)=>assert.equal(v,three.mealTarget[i]*1.5));
 await editStep(1);await page.locator('[name=mealCount][value="3"]').check({force:true});await page.locator('[data-flow-next="2"]').click();await page.locator('[data-flow-next="3"]').click();await submitResult();
 await shot('results-desktop');note('결과에서 기본 정보 수정·2끼/3끼 목표·식당 탭 유지');
 await editStep(2);await page.locator('#allergyToggle').click();for(const n of [2,9])await page.locator(`#allergyOptions input[value="${n}"]`).check();await page.locator('#allergyDone').click();await submitResult();
 assert.equal(await page.locator('.card').count(),6);assert(await page.locator('.allergy-excluded-card').count()>0);
 for(const c of await page.locator('.allergy-excluded-card').all()){assert.equal(await c.locator('.rank-pill').count(),0);assert.equal(await c.locator('.card-more').count(),0);}
 note('제외 카드 회색·후순위·무순위·선택 불가 및 전체 메뉴 수 유지');
 await editStep(2);await page.locator('#allergyToggle').click();for(const input of await page.locator('#allergyOptions input').all())await input.check({force:true});await page.locator('#allergyDone').click();await submitResult();
 assert.equal(await page.locator('.allergy-excluded-card').count(),6);assert.equal(await page.locator('.rank-pill').count(),0);assert(await page.locator('.empty-note').isVisible());note('모든 메뉴 알레르기 제외 시 안내 유지');
 await editStep(2);await page.locator('#allergyToggle').click();await page.locator('#allergyClear').click();for(const n of [2,9])await page.locator(`#allergyOptions input[value="${n}"]`).check();await page.locator('#allergyDone').click();await submitResult();
 const stored=await page.evaluate(()=>localStorage.getItem('hyu-menu-guide.profile.v1'));assert(stored);
 await page.reload();await page.waitForFunction(()=>!document.querySelector('#personalSubmit').disabled);assert.equal(await stage(),'0');await page.locator('#guideStart').click();assert.equal(await page.locator('[name=age]').inputValue(),'22');assert(await page.locator('#rememberProfile').isChecked());
 const state=await context.storageState(),reopened=await browser.newContext({storageState:state});const restored=await reopened.newPage();await restored.goto(url+'?date=2026-11-04');await restored.waitForFunction(()=>!document.querySelector('#personalSubmit').disabled);await restored.locator('#guideStart').click();assert.equal(await restored.locator('[name=weightKg]').inputValue(),'65');await reopened.close();
 await page.evaluate(()=>localStorage.setItem('unrelated-test','keep'));await page.locator('#deleteProfile').click();assert.equal(await page.evaluate(()=>localStorage.getItem('hyu-menu-guide.profile.v1')),null);assert.equal(await page.evaluate(()=>localStorage.getItem('unrelated-test')),'keep');await page.locator('[name=weightKg]').fill('66');assert.equal(await page.evaluate(()=>localStorage.getItem('hyu-menu-guide.profile.v1')),null);note('기억 동의·새로고침/재접속 복원·삭제·미동의 영구 저장 없음');
 await page.locator('[name=weightKg]').fill('65');await page.locator('[data-flow-next="2"]').click();await page.locator('#allergyToggle').click();await page.locator('#allergyClear').click();await page.locator('#allergyDone').click();await submitResult();
 await page.locator('#dateStrip button').filter({hasText:'11/3'}).click();assert((await page.locator('#dayTitle').innerText()).includes('2026.11.03'));
 const expectedPhotos=rows.filter(r=>r.date==='2026-11-03'&&r.photo).length;assert.equal(await page.locator('#shopGrid .card img').count(),expectedPhotos);
 await page.locator('#shopGrid .card img').evaluateAll(imgs=>{imgs.forEach(i=>i.loading='eager');return Promise.race([Promise.all(imgs.map(i=>i.decode().catch(()=>{}))),new Promise(r=>setTimeout(r,5000))]);});
 assert(await page.locator('#shopGrid .card img').evaluateAll(imgs=>imgs.every(i=>i.naturalWidth>0)));note('결과 날짜 변경·기존 사진 전체 로딩');
 await page.setViewportSize({width:390,height:844});assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
 const rects=await page.locator('.card').evaluateAll(cards=>cards.map(c=>{const r=c.getBoundingClientRect();return {left:r.left,top:r.top};}));for(let i=1;i<rects.length;i++){assert.equal(rects[i].left,rects[0].left);assert(rects[i].top>rects[i-1].top);}
 await shot('results-mobile');await editStep(2);await page.locator('#allergyToggle').click();assert(await page.locator('#allergyPanel').isVisible());assert(await page.locator('#allergyOptions').evaluate(el=>el.scrollHeight>el.clientHeight));await shot('allergy-mobile');note('모바일 세로 목록·가로 넘침 없음·스크롤 드롭다운');
 const visibleDates=await page.locator('#dateStrip button').evaluateAll(buttons=>buttons.map(b=>b.getAttribute('aria-label').slice(0,10).replaceAll('.','-')));
 const expectedDates=[...new Set(rows.map(r=>r.date))].filter(d=>d>='2026-10-26').sort();
 assert.deepEqual(visibleDates,expectedDates);
 const preservedDates=await page.evaluate(()=>({count:BASE_DATA.length,earliest:BASE_DATA.map(r=>r.date).sort()[0],older:BASE_DATA.filter(r=>r.date<'2026-10-26').length}));
 assert.equal(preservedDates.count,rows.length);assert(preservedDates.earliest<'2026-10-26');assert(preservedDates.older>0);
 note('추천 날짜는 10/26 이후만 표시하고 이전 메뉴 데이터 전체는 유지');
 assert.deepEqual(errors,[]);fs.writeFileSync(path.join(output,'browser-report.json'),JSON.stringify({checks,modeChecks,errors},null,2));console.log(JSON.stringify({passed:checks.length,checks,errors},null,2));
})().catch(error=>{console.error(error);process.exitCode=1;}).finally(async()=>{await browser?.close();});
