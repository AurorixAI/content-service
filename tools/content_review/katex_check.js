const katex = require('/Users/arslan/Desktop/ALGO/algo-front/node_modules/katex');
const J = require(process.argv[2]); let bad = 0, n = 0;
for (const [id, arr] of Object.entries(J)) for (const s of arr) {
  if (!s) continue;
  const parts = []; const re = /\$\$([\s\S]+?)\$\$|\$([^$]+?)\$/g; let m;
  while ((m = re.exec(s))) parts.push([m[1] || m[2], !!m[1]]);
  for (const [tex, disp] of parts) { n++;
    try { katex.renderToString(tex, {throwOnError: true, displayMode: disp, strict: 'ignore'}); }
    catch (e) { bad++; console.log(id, '|', e.message.slice(0, 160)); } }
}
console.log('fragments', n, 'errors', bad);
