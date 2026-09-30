const katex = require('/Users/arslan/Desktop/ALGO/algo-front/node_modules/katex');
const fs = require('fs'); const J = require(process.argv[2]); const ids = process.argv[3].split(',');
const esc = s => s.replace(/&/g,'&amp;').replace(/</g,'&lt;');
const r = s => s.replace(/\$\$([\s\S]+?)\$\$|\$([^$]+?)\$|([^$]+)/g, (m, d, i, t) => t !== undefined ? esc(t) :
  katex.renderToString(d || i, {displayMode: !!d, throwOnError: false, strict: 'ignore'}));
let html = `<html><head><meta charset="utf-8"><link rel="stylesheet" href="file:///Users/arslan/Desktop/ALGO/algo-front/node_modules/katex/dist/katex.min.css"><style>body{font-family:sans-serif;max-width:900px;margin:20px}div.t{border-bottom:1px solid #ccc;padding:12px 0}</style></head><body>`;
for (const id of ids) html += `<div class="t"><b>${id}</b><p>${r(J[id][0])}</p><p><i>Ключ:</i> ${r(J[id][1] || "(без изменений)")}</p></div>`;
fs.writeFileSync(process.argv[4], html + '</body></html>');
