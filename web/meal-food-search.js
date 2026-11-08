"use strict";

let catalog;
const normalize = value => value.normalize("NFKC").toLowerCase().replace(/\s+/g, "");

async function loadCatalog() {
  const response = await fetch("./meal-food-index.json.gz");
  if (!response.ok) throw new Error("음식 DB를 불러오지 못했습니다.");
  const bytes = new Uint8Array(await response.arrayBuffer());
  const stream = new Blob([bytes]).stream();
  const decoded = bytes[0] === 0x1f && bytes[1] === 0x8b
    ? stream.pipeThrough(new DecompressionStream("gzip")) : stream;
  return new Response(decoded).json();
}

self.onmessage = async ({data: {id, query}}) => {
  try {
    catalog ??= loadCatalog().catch(error => {
      catalog = null;
      throw error;
    });
    const rows = await catalog;
    const key = normalize(query);
    const groups = {cooked: [[], [], []], ingredient: [[], [], []], processed: [[], [], []]};
    const counts = {cooked: 0, ingredient: 0, processed: 0};
    for (const row of rows) {
      const name = row[10];
      const position = name.indexOf(key);
      if (position < 0) continue;
      const kind = row[0].split(":", 1)[0];
      counts[kind]++;
      const priority = name === key ? 0 : position === 0 ? 1 : 2;
      if (groups[kind][priority].length < 20) groups[kind][priority].push(row.slice(0, 10));
    }
    for (const kind of Object.keys(groups)) groups[kind] = groups[kind].flat().slice(0, 20);
    self.postMessage({id, groups, counts});
  } catch {
    self.postMessage({id, error: "음식 DB를 열 수 없습니다. 다시 검색하거나 직접 영양정보를 입력해주세요."});
  }
};
