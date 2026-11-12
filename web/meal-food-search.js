"use strict";
importScripts('./meal-serving.js?v=category-20261112');

let catalog;
let recipeUnavailable=false;
const normalize = value => value.normalize("NFKC").toLowerCase().replace(/\s+/g, "");

async function loadCatalog() {
  const response = await fetch("./meal-food-index.json.gz");
  if (!response.ok) throw new Error("음식 DB를 불러오지 못했습니다.");
  const bytes = new Uint8Array(await response.arrayBuffer());
  const stream = new Blob([bytes]).stream();
  const decoded = bytes[0] === 0x1f && bytes[1] === 0x8b
    ? stream.pipeThrough(new DecompressionStream("gzip")) : stream;
  const base = await new Response(decoded).json();
  // Recipes are existing per100 cache values, not new serving-based calculations.
  const recipes = await fetch('./meal-recipe-index.json?v=category-20261112').then(response=>{
    if(!response.ok)throw Error('recipe index');
    return response.json();
  }).catch(()=>{recipeUnavailable=true;return [];});
  return base.concat(recipes);
}

self.onmessage = async ({data: {id, query}}) => {
  try {
    catalog ??= loadCatalog().catch(error => {
      catalog = null;
      throw error;
    });
    const rows = await catalog;
    const requested=MealServing.searchQuery(query);
    let matchedQuery=requested,portionQuery=null;
    if (/^(미니|꼬마).+/.test(normalize(requested))&&!rows.some(row=>row[10].includes(normalize(requested)))) {
      matchedQuery=requested.trim().replace(/^(미니|꼬마)\s*/,'');
      portionQuery=requested;
    }
    const key = normalize(matchedQuery);
    const groups = {cooked: [], recipe: [], processed: [], ingredient: []};
    const counts = {cooked: 0, recipe: 0, processed: 0, ingredient: 0};
    const priority = row=>row[10]===key?0:row[10].startsWith(key)?1:2;
    const sourceRank = row=>MealServing.sourcePriority({id:row[0],name:row[1],detail:row[3],foodType:row[4],basis:row[5]});
    const compare = (a,b)=>priority(a)-priority(b)||sourceRank(a)-sourceRank(b);
    for (const row of rows) {
      const name = row[10];
      const position = name.indexOf(key);
      if (position < 0) continue;
      const kind = row[0].split(":", 1)[0];
      counts[kind]++;
      groups[kind].push(row);
    }
    for (const kind of Object.keys(groups)) groups[kind] = groups[kind].sort(compare).slice(0,20);
    const selected=Object.values(groups).flat().sort(compare);
    const pack=row=>[...row.slice(0,10),row[11]??null];
    const ordered=selected.map(pack);
    for (const kind of Object.keys(groups)) groups[kind] = groups[kind].map(pack);
    self.postMessage({id, groups, ordered, counts, matchedQuery,portionQuery,recipeUnavailable});
  } catch {
    self.postMessage({id, error: "음식 DB를 열 수 없습니다. 다시 검색하거나 직접 영양정보를 입력해주세요."});
  }
};
