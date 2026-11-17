const {test}=require('node:test'),assert=require('node:assert/strict'),fs=require('node:fs'),path=require('node:path');
const Components=require('./component-nutrition.js');
const rows=JSON.parse(fs.readFileSync(path.join(__dirname,'site_data.json'),'utf8'));
test('real rice serving reuses contribution values, without applying the serving factor again',()=>{
 const row=rows.find(r=>r.date==='2026-11-16'&&r.main==='고구마치즈돈까스');
 const values=Components.get(row,row.components.indexOf('쌀밥')).values;
 assert.equal(values.kcal,348.6);
 assert(Math.abs(values.carb-78.393)<1e-10);
 assert.equal(values.protein,7.056);assert.equal(values.fat,.672);
});
test('missing/unmatched values stay unknown; actual zero stays numeric zero',()=>{
 const item={components:['A','B','C'],itemDetails:[
  {display:'A',matched:true,contrib:{kcal:10,carb:0,protein:1,fat:0},missing:['protein']},
  {display:'B',matched:false,contrib:{kcal:0,carb:0,protein:0,fat:0}},
 ]};
 assert.deepEqual(Components.get(item,0).values,{kcal:10,carb:0,protein:null,fat:0});
 for(const i of [1,2])assert(Object.values(Components.get(item,i).values).every(v=>v===null));
});
test('same-name component occurrences use their own original contribution',()=>{
 const row=rows.find(r=>r.date==='2026-07-28'&&r.main==='스팸김치마요덮밥');
 const indices=row.components.map((n,i)=>n==='배추김치'?i:null).filter(i=>i!==null);
 assert.equal(Components.get(row,indices[0]).values.kcal,11.4);
 assert.equal(Components.get(row,indices[1]).values.kcal,15.2);
});
test('only existing display aliases connect old labels; substring matches do not',()=>{
 const row=rows.find(r=>r.date==='2026-11-06'&&r.main==='황태무침비빔밥');
 assert(Components.get(row,row.components.indexOf('황태무침')).detailCount>0);
 assert.equal(Components.get({components:['김치'],itemDetails:[{display:'김치볶음밥',contrib:{kcal:500}}]},0).values.kcal,null);
});
test('ambiguous duplicate labels do not repeat a single value for both buttons',()=>{
 const row={components:['A','A'],itemDetails:[{display:'A',contrib:{kcal:10,carb:1,protein:1,fat:1}}]};
 assert.equal(Components.get(row,0).values.kcal,null);assert.equal(Components.get(row,1).values.kcal,null);
});
test('rendered controls are accessible and component names are escaped',()=>{
 const html=Components.render({components:['<img onerror=bad()>']});
 assert(html.includes('type="button"'));assert(html.includes('aria-expanded="false"'));
 assert(html.includes('&lt;img onerror=bad()&gt;'));assert(!html.includes('<img'));
});
test('all current labels connect by exact occurrence or existing alias, without mutating input',()=>{
 const before=JSON.stringify(rows);let count=0;
 for(const row of rows)for(let i=0;i<(row.components??[]).length;i++){
  const result=Components.get(row,i);assert(result.detailCount>0,`${row.date}: ${row.components[i]}`);count++;
 }
 assert(count>3000);assert.equal(JSON.stringify(rows),before);
});
