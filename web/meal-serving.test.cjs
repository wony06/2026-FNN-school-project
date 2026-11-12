const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const Serving=require('./meal-serving.js'),table=require('./meal-serving-rules.json');
const food=(name,basis='100g',extra={})=>({id:'cooked:test',name,basis,kind:'cooked',...extra});
const amount=(name,unit='g',extra={})=>Serving.lookup(food(name,'100'+unit,extra),table);
test('all provided category amounts are applied independently for g/mL',()=>{
 const pairs=[['쌀밥',210,258],['김치볶음밥',289,258],['비빔밥',418,417],['비프하이라이스',418,417],['짜장밥',418,417],['차돌짬뽕밥',418,417],['우동',497,497],['라면',497,497],['짜장면',497,497],['비빔국수',497,497],['비빔냉면',497,497],['된장국',283,288],['동태탕',283,288],['된장찌개',283,201],['버섯전골',283,201],['갈비찜',283,201]];
 for(const [name,g,ml] of pairs){
  assert.equal(amount(name,'g',{foodType:name==='동태탕'?'국 및 탕류':''}).amount,g,name);
  assert.equal(amount(name,'mL',{foodType:name==='동태탕'?'국 및 탕류':''}).amount,ml,name);
 }
});
test('sides, main protein and special categories follow the supplied table',()=>{
 for(const [name,g] of [['감자조림',44],['새우젓갈',44],['어묵볶음',80],['배추김치',70],['시금치나물',70],['오이무침',70],['두부구이',96],['부추전',96],['샐러드',71],['단무지',72.2],['제육볶음',151],['돈까스',151],['함박스테이크',151],['고등어구이',70],['미니우동',120],['크림파스타',172],['잡채',72.2]])assert.equal(amount(name).amount,g,name);
 assert.equal(amount('잡채','mL').amount,150);
 assert.equal(amount('타르타르소스','mL').amount,9);
});
test('one-unit-only categories never inherit the other unit or any DB serving',()=>{
 for(const [name,unit] of [['미니우동','mL'],['스파게티','mL'],['간장','g'],['어묵볶음','mL'],['돈까스','mL']])assert.equal(amount(name,unit).state,'unit_unavailable',name);
 assert.equal(amount('김치볶음밥','g',{servingWeight:'999g',serving:1,grams:8}).amount,289);
 assert.equal(amount('미니어묵볶음','g',{servingWeight:'1000g'}).amount,80);
 assert.equal(amount('미등록음식','g',{servingWeight:'100g'}).state,'missing');
 assert.equal(amount('사과','g',{kind:'ingredient',id:'ingredient:1'}).state,'missing');
 assert.equal(amount('하이라이스분말').state,'missing');
 assert.equal(amount('우동','g',{kind:'processed',foodType:'숙면'}).state,'missing');
});
test('basis amount is parsed as a quantity, never as a serving and never inferred from origin',()=>{
 assert.deepEqual(Serving.reference(food('밥','1회 제공량 (200mL)')),{amount:200,unit:'mL'});
 assert.equal(Serving.lookup(food('쌀밥','200g'),table).amount,210);
 assert.equal(Serving.lookup(food('쌀밥','1인분'),table).state,'unknown_basis');
 assert.equal(amount('쌀밥','g',{detail:'산업체급식'}).amount,210);
});
test('extra noodles are not another automatic portion; main dish name remains searchable',()=>{
 assert.equal(amount('라면사리').state,'extra_noodles');
 assert.equal(Serving.searchQuery('부대찌개&라면사리'),'부대찌개');
 assert.equal(Serving.searchQuery('우동사리'),'우동사리');
 assert.equal(Serving.searchQuery('쌀밥/흑미밥'),'쌀밥/흑미밥');
});
test('source priority: side g analysis → household → recipe → processed → ingredient',()=>{
 const base=food('어묵볶음');
 const candidates=[{...base,kind:'ingredient'},{...base,kind:'processed'},{...base,kind:'recipe'},
  {...base,detail:'가정식(분석 함량)'},{...base,detail:'외식(분석함량)'}, {...base,basis:'100ml',detail:'산업체급식(재료량 기반 산출 함량)'}];
 assert.deepEqual(candidates.map(Serving.sourcePriority),[40,30,20,1,0,50]);
 const soup=food('미역국');
 assert(Serving.sourcePriority({...soup,basis:'100ml',detail:'산업체급식(재료량 기반 산출 함량)'})<Serving.sourcePriority({...soup,detail:'외식(분석함량)'}));
});
test('real search worker applies source priorities across groups before truncation',async()=>{
 const row=(id,name,detail,basis='100g')=>[id,name,'source',detail,'볶음류',basis,100,1,1,1,Serving.normalize(name)];
 const rows=[...Array.from({length:25},(_,i)=>row('cooked:other'+i,'어묵볶음','외식(프랜차이즈 등 업체 제공 영양정보)')),
  row('cooked:preferred','어묵볶음','외식(분석함량)'),row('cooked:home','어묵볶음','가정식(분석 함량)'),row('processed:1','어묵볶음','maker'),row('ingredient:1','어묵볶음','raw')];
 let message;
 const context={self:{postMessage:value=>message=value},MealServing:Serving,importScripts(){},Blob,Response,DecompressionStream,
  fetch:async url=>new Response(JSON.stringify(url.includes('recipe-index')?[row('recipe:1','어묵볶음','recipe')]:rows))};
 vm.runInNewContext(fs.readFileSync(path.join(__dirname,'meal-food-search.js'),'utf8'),context);
 await context.self.onmessage({data:{id:1,query:'어묵볶음'}});
 assert.equal(message.error,undefined);
 assert.deepEqual(Array.from(message.ordered.slice(0,5),row=>row[0]),['cooked:preferred','cooked:home','recipe:1','processed:1','ingredient:1']);
 assert.equal(message.groups.cooked.length,20);
});
