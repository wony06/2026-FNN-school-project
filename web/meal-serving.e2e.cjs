// Serve web/ statically; NODE_PATH must contain Playwright. Uses isolated test storage.
const {chromium}=require('playwright'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),os=require('node:os'),zlib=require('node:zlib');
const Serving=require('./meal-serving.js'),table=require('./meal-serving-rules.json');
const catalog=JSON.parse(zlib.gunzipSync(fs.readFileSync(path.join(__dirname,'meal-food-index.json.gz'))));
const byId=new Map(catalog.map(r=>[r[0],r]));
const profile={version:1,consent:true,profile:{sex:'male',age:'22',heightCm:'170',weightKg:'65',activity:'1',mealCount:'3',goal:'balanced',monthlyLossKg:'',allergies:[]}};
const url=process.env.HYU_TEST_URL||'http://127.0.0.1:8790/';
const output=process.env.HYU_SERVING_OUTPUT||path.join(os.tmpdir(),'hyu-category-serving');fs.mkdirSync(output,{recursive:true});
const key='hyu-menu-guide.meal-diary.v1',checks=[],errors=[],near=(a,b)=>assert(Math.abs(a-b)<1e-8,`${a} != ${b}`);
const fmt=n=>new Intl.NumberFormat('ko-KR',{maximumFractionDigits:1}).format(n);
let browser;
(async()=>{
 browser=await chromium.launch({headless:true,executablePath:process.env.HYU_BROWSER_PATH||'C:/Program Files/Google/Chrome/Application/chrome.exe'});
 const context=await browser.newContext({viewport:{width:1440,height:1000}}),page=await context.newPage();
 page.on('pageerror',e=>errors.push(e.message));
 await context.addInitScript(p=>localStorage.setItem('hyu-menu-guide.profile.v1',JSON.stringify(p)),profile);
 await page.clock.install({time:new Date('2026-11-12T03:00:00Z')});
 async function open(){await page.goto(url+'?date=2026-11-03&v=category-serving');await page.waitForFunction(()=>!document.querySelector('#personalSubmit').disabled);await page.locator('#guideResume').click();await page.locator('#mealDiaryTab').click();}
 const records=()=>page.evaluate(k=>JSON.parse(localStorage.getItem(k)).records,key);
 async function choose(row,meal='breakfast'){
  await page.locator(`[data-meal-add=${meal}]`).click();await page.locator('#mealFoodQuery').fill(row[1]);await page.locator('#mealFoodSearch').click();
  let result=page.locator('.meal-search-result').filter({hasText:row[0].split(':').slice(1).join(':')});
  if(row[0].startsWith('recipe:'))result=result.filter({hasText:'기존 레시피 재료매칭 계산값'});
  await result.first().click();
 }
 async function save(){await page.locator('#mealEntrySave').click();await page.locator('#mealEntryDialog').waitFor({state:'hidden'});}
 async function standard(row,expected,meal='breakfast'){
  await choose(row,meal);assert(await page.locator('#mealPortionServing').isChecked());
  assert((await page.locator('#mealServingLabel').innerText()).includes(String(expected)));
  await save();const record=(await records()).at(-1);assert.equal(record.amount,expected);
  ['kcal','carb','protein','fat'].forEach((n,i)=>near(record.nutrients[n],row[6+i]*expected/100));return record;
 }
 await open();await page.locator('#mealDiaryConsent').check();
 const fried=byId.get('processed:P123-201020300-6134');await standard(fried,289);
 near((await records())[0].nutrients.kcal,485.52);checks.push('스크린샷의 김치볶음밥 제품: DB 자체 serving 대신 289g·485.52kcal');
 await page.locator('[data-meal-edit]').first().click();await page.locator('#mealPortionDirect').check();await page.locator('#mealEntryAmount').fill('100');await save();
 near((await records())[0].nutrients.kcal,168);checks.push('직접 100g 수정 시 열량·탄단지 비례 재계산');
 await standard(byId.get('cooked:D301-022000000-0001'),210);
 await standard(byId.get('cooked:D301-018000000-0002'),418,'lunch');
 await standard(byId.get('cooked:D701-018000000-0001'),417,'lunch');checks.push('쌀밥 210g, 비빔밥 418g/417mL 단위별 적용');
 await standard(byId.get('cooked:D705-223000000-0001'),288,'dinner');
 const stew=catalog.find(r=>r[1].includes('된장찌개')&&r[3].startsWith('산업체급식')&&r[5]==='100ml');assert(stew);await standard(stew,201,'dinner');
 checks.push('국·탕 288mL와 찌개·전골 201mL 분리');
 const sauce=catalog.find(r=>r[0].startsWith('cooked:')&&r[5]==='100ml'&&Serving.classify({id:r[0],name:r[1],foodType:r[4]})==='sauce');assert(sauce);await standard(sauce,9,'snack');
 await choose(byId.get('processed:P113-206020400-6441'),'snack');assert(await page.locator('#mealPortionServing').isDisabled());
 assert.match(await page.locator('#mealServingHint').innerText(),/g 표준량이 없습니다/);await page.locator('#mealEntryAmount').fill('9');await save();checks.push('소스 9mL만 자동 적용, g 레코드는 직접 입력 유지');
 const apple=byId.get('ingredient:1508');await choose(apple,'snack');assert(await page.locator('#mealPortionServing').isDisabled());
 for(const value of ['0','-1']){await page.locator('#mealEntryAmount').fill(value);assert(await page.locator('#mealEntrySave').isDisabled());}
 await page.locator('#mealEntryAmount').fill('100');await save();checks.push('표에 없는 원재료는 직접 입력, 0·음수 차단');
 await page.locator('[data-meal-add=snack]').click();await page.locator('#mealFoodQuery').fill('어묵볶음');await page.locator('#mealFoodSearch').click();
 await page.locator('.meal-search-result').first().waitFor();assert.match(await page.locator('.meal-search-result').first().innerText(),/가정식\(분석 함량\)|외식\(분석함량\)/);await page.locator('#mealEntryClose').click();
 await page.locator('[data-meal-add=snack]').click();await page.locator('#mealFoodQuery').fill('비빔밥');await page.locator('#mealFoodSearch').click();
 await page.locator('.meal-search-result').first().waitFor();assert.match(await page.locator('.meal-search-result').first().innerText(),/산업체급식/);await page.locator('#mealEntryClose').click();checks.push('실제 검색에서 반찬 g 분석값 우선, 밥 산업체급식 우선');
 const recipes=require('./meal-recipe-index.json');
 const recipe=recipes.find(r=>Serving.lookup({id:r[0],name:r[1],foodType:r[4],basis:r[5]},table).state==='available');assert(recipe);
 const recipeAmount=Serving.lookup({id:recipe[0],name:recipe[1],foodType:recipe[4],basis:recipe[5]},table).amount;
 const recipeRecord=await standard(recipe,recipeAmount,'snack');assert.equal(recipeRecord.base.id,recipe[0]);
 assert.deepEqual(recipeRecord.incomplete,recipe[11].incomplete);checks.push('기존 레시피 per100 재사용 및 미확인 영양값 표시 보존');
 const all=await records(),sum=n=>all.reduce((total,r)=>total+r.nutrients[n],0);
 assert.equal(await page.locator('.meal-energy-number strong').innerText(),fmt(sum('kcal')));
 const displayed=await page.locator('.meal-macro-value').allTextContents();
 ['carb','protein','fat'].forEach((n,i)=>{
  assert(displayed[i].startsWith(fmt(sum(n))+' g'));
  assert.equal(displayed[i].includes('확인된 값'),all.some(r=>r.incomplete.includes(n)));
 });
 const kcal=sum('carb')*4+sum('protein')*4+sum('fat')*9;
 assert.deepEqual(await page.locator('.meal-breakdown-legend strong').allTextContents(),[['carb',4],['protein',4],['fat',9]].map(([n,f])=>fmt(sum(n)*f/kcal*100)+'%'));
 checks.push('아침·점심·저녁·간식 총합 및 기존 4/4/9 도넛 그래프 검산');
 await page.reload();await page.locator('#guideResume').click();await page.locator('#mealDiaryTab').click();assert.deepEqual(await records(),all);
 await page.locator('[data-meal-delete]').last().click();assert.equal((await records()).length,all.length-1);checks.push('새로고침 복원과 삭제 후 합계 갱신');
 await choose(fried);await page.screenshot({path:path.join(output,'desktop-dialog.png')});await page.locator('#mealEntryClose').click();
 await page.setViewportSize({width:390,height:844});await choose(fried);assert(await page.locator('#mealServingLabel').isVisible());
 assert(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));assert(await page.locator('#mealEntryDialog').evaluate(e=>e.getBoundingClientRect().width<=innerWidth));
 await page.screenshot({path:path.join(output,'mobile-dialog.png')});await page.locator('#mealEntryClose').click();checks.push('PC·390px 모바일에서 1인분/직접 입력 및 모달 가로 넘침 없음');
 // The historical serving record must not silently become today's category quantity.
 const legacy={...all[1],id:'legacy',portion:'serving',amount:190,nutrients:{kcal:315.4,carb:70.927,protein:6.384,fat:0.608}};delete legacy.unit;delete legacy.servingReference;
 await page.evaluate(({key,legacy})=>localStorage.setItem(key,JSON.stringify({consent:true,records:[legacy]})),{key,legacy});
 await page.reload();await page.locator('#guideResume').click();await page.locator('#mealDiaryTab').click();await page.locator('[data-meal-edit]').click();assert.match(await page.locator('#mealServingLabel').innerText(),/190 g/);await save();
 assert.equal((await records())[0].amount,190);near((await records())[0].nutrients.kcal,315.4);checks.push('과거 단위 없는 g 기록과 기존 190g 1인분 보존');
 await page.route('**/meal-serving-rules.json*',r=>r.abort());await page.reload();await page.locator('#guideResume').click();await page.locator('#mealDiaryTab').click();await choose(fried);
 assert(await page.locator('#mealPortionServing').isDisabled());await page.locator('#mealEntryAmount').fill('100');await save();near((await records()).at(-1).nutrients.kcal,168);
 checks.push('표 로딩 실패 시 임의 1인분 없이 직접 입력 가능');
 assert.deepEqual(errors,[]);const report={passed:checks.length,checks,errors};fs.writeFileSync(path.join(output,'report.json'),JSON.stringify(report,null,2));console.log(JSON.stringify(report,null,2));
})().catch(e=>{console.error(e);process.exitCode=1;}).finally(async()=>{await browser?.close();});
