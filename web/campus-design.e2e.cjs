const {chromium}=require('playwright');
const fs=require('fs'),path=require('path'),assert=require('node:assert/strict');
const out=process.env.HYU_FLOW_OUTPUT||path.join(require('os').tmpdir(),'hyu-campus-design');fs.mkdirSync(out,{recursive:true});
const url=process.env.HYU_TEST_URL||'http://127.0.0.1:8790/';
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:'C:/Program Files/Google/Chrome/Application/chrome.exe'});
 const report={screens:[],errors:[],checks:[]};
 for(const [device,width,height] of [['desktop',1440,1000],['mobile',390,844]]){
  const context=await browser.newContext({viewport:{width,height}}),page=await context.newPage();page.on('pageerror',e=>report.errors.push(e.message));

  async function editStep(step){
   const button=page.locator(`[data-edit-step="${step}"]`);
   if(!await button.isVisible()) await page.locator('#resultSettingsMenu > summary').click();
   await button.click();
  }
  await page.clock.install({time:new Date('2026-11-03T03:00:00Z')});
 await page.goto(url+'?date=2026-11-03&v=campus-design-v2');await page.waitForFunction(()=>!document.querySelector('#personalSubmit').disabled);
  await page.evaluate(()=>Promise.race([document.fonts.ready,new Promise(r=>setTimeout(r,4000))]));
  async function capture(step){
   assert.equal(await page.locator('body').getAttribute('data-flow-step'),String(step));
   assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
   if(step>0)assert.equal(await page.locator('[aria-current=step]').getAttribute('data-progress-step'),String(step));
   await page.waitForTimeout(200);await page.evaluate(()=>scrollTo(0,0));await page.screenshot({path:path.join(out,`${device}-${step}.png`),fullPage:true});report.screens.push(`${device}-${step}`);
  }
  await capture(0);await page.locator('#guideStart').click();
  await page.locator('[name=sex]').selectOption('male');for(const [name,value] of [['age','22'],['heightCm','170'],['weightKg','65']])await page.locator(`[name=${name}]`).fill(value);
  await page.locator('.activity-option').nth(1).click();await capture(1);
  const inputs=await page.locator('.profile-grid input,.profile-grid select').evaluateAll(es=>es.map(e=>e.getBoundingClientRect().height));assert(inputs.every(h=>h===inputs[0]));
  await page.locator('[data-flow-next="2"]').click();await page.locator('.goal-option').filter({has:page.locator('[value=balanced]')}).click();await page.mouse.move(0,0);await capture(2);
  report[device+'Selected']=await page.locator('.goal-option:has(input:checked)>span').evaluate(e=>{const s=getComputedStyle(e);return {color:s.color,background:s.backgroundColor,border:s.borderColor,font:s.fontFamily}});
  await page.locator('[data-flow-next="3"]').click();await capture(3);
  await page.locator('#allergyToggle').click();assert(await page.locator('#allergyOptions').evaluate(e=>e.scrollHeight>e.clientHeight));await page.screenshot({path:path.join(out,`${device}-allergy-open.png`),fullPage:true});await page.locator('#allergyDone').click();
  await page.locator('#personalSubmit').click();
  await page.locator('.card img').evaluateAll(imgs=>{imgs.forEach(i=>i.loading='eager');return Promise.race([Promise.all(imgs.map(i=>i.decode().catch(()=>{}))),new Promise(r=>setTimeout(r,4000))])});
  await capture(4);assert(await page.locator('.card img').evaluateAll(es=>es.every(e=>e.naturalWidth>0)));
  const box=await page.locator('.card').first().evaluate(e=>{let img=e.querySelector('.card-photo').getBoundingClientRect(),name=e.querySelector('.card-name').getBoundingClientRect();return {imageRight:img.right,nameLeft:name.left,height:e.getBoundingClientRect().height}});assert(box.imageRight<box.nameLeft);report[device+'Card']=box;
  assert.equal(await page.locator('.card .nutrition-mini dt').count(),18);
  const notes=page.locator('.menu-notes').first();if(await notes.count()){await notes.locator('summary').click();assert(await notes.evaluate(e=>e.open));assert(!(await page.locator('#sheet').getAttribute('class')).includes('open'));await notes.locator('summary').click();}
  await page.locator('.card-more').first().click();await page.locator('#sheet.open').waitFor();assert(await page.locator('#sheetBody').isVisible());await page.waitForTimeout(350);assert(await page.locator('#sheet').evaluate(e=>{const r=e.getBoundingClientRect();return r.left>=-1&&r.right<=innerWidth+1}));await page.screenshot({path:path.join(out,`${device}-detail.png`),fullPage:false});await page.locator('#sheetClose').click();
  await editStep(3);await page.locator('#allergyToggle').click();await page.locator('#allergyOptions input[value="2"]').check();await page.locator('#allergyDone').click();await page.locator('#personalSubmit').click();
  const excluded=page.locator('.allergy-excluded-card');assert(await excluded.count()>0);assert.equal(await excluded.locator('.rank-pill').count(),0);assert.equal(await excluded.locator('.card-more').count(),0);
  await page.screenshot({path:path.join(out,`${device}-excluded.png`),fullPage:true});report.checks.push(device+': all steps, progress, uniform fields, dropdown scroll, photos, left-right card, notes, detail, exclusions');
  for(const narrow of [320,768,1024]){
   await page.setViewportSize({width:narrow,height:900});
   for(const step of [1,2,3]){await editStep(step);assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));await page.locator('[data-flow-next="2"]').isVisible().then(async visible=>{if(visible)await page.locator('[data-flow-next="2"]').click()});if(await page.locator('[data-flow-next="3"]').isVisible())await page.locator('[data-flow-next="3"]').click();await page.locator('#personalSubmit').click();assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));}
  }
  report.checks.push(device+': 320/768/1024px onboarding and results without horizontal overflow');
  await context.close();
 }
 assert.deepEqual(report.errors,[]);await browser.close();fs.writeFileSync(path.join(out,'visual-report.json'),JSON.stringify(report,null,2));console.log(JSON.stringify(report,null,2));
})().catch(e=>{console.error(e);process.exit(1)});
