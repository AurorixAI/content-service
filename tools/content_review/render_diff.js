// Render-diff with the site renderer (algo-front/src/components/ui/math-renderer.tsx, real katex).
// usage: node render_diff.js before.json after.json [kinds.json]
//   before/after: {id: [question_text, question_latex]}; prints per id: SAME (visible text identical after
//   whitespace normalisation) or the first differing window.  Line breaks are kept as "⏎" in the second line.
const fs = require('fs'), path = require('path'), Module = require('module');
const FRONT = '/Users/arslan/Desktop/ALGO/algo-front';
const sucrase = require(path.join(FRONT, 'node_modules/sucrase'));
const src = fs.readFileSync(path.join(FRONT, 'src/components/ui/math-renderer.tsx'), 'utf8');
const js = sucrase.transform(src, { transforms: ['typescript', 'jsx', 'imports'] }).code;
const origResolve = Module._resolveFilename;
Module._resolveFilename = function (req, ...a) {
  if (req === 'katex') return require.resolve(path.join(FRONT, 'node_modules/katex'));
  if (req === 'react') return 'react-stub';
  if (req.endsWith('lib/utils')) return 'utils-stub';
  if (req.endsWith('math-fit')) return 'fit-stub';
  return origResolve.call(this, req, ...a);
};
require.cache['react-stub'] = { id: 'react-stub', filename: 'react-stub', loaded: true, exports: { useMemo: (f) => f(), useEffect() {}, useLayoutEffect() {}, useRef: () => ({ current: null }), default: {} } };
require.cache['fit-stub'] = { id: 'fit-stub', filename: 'fit-stub', loaded: true, exports: { fitMathElement() {} } };
require.cache['utils-stub'] = { id: 'utils-stub', filename: 'utils-stub', loaded: true, exports: { cn: (...x) => x.filter(Boolean).join(' ') } };
const m = new Module('/mr.js'); m.filename = '/mr.js'; m.paths = Module._nodeModulePaths(FRONT);
m._compile(js, '/mr.js');
const { renderMathText } = m.exports;
function visible(s, mode) {
  const html = renderMathText(s, true, mode);
  const withBr = html.replace(/<br\s*\/?>/g, '⏎');
  const txt = withBr.replace(/<span class="katex-mathml">[\s\S]*?<\/span><span class="katex-html"/g, '<span class="katex-html"').replace(/<[^>]*>/g, '')
    .replace(/&lt;/g, '<').replace(/&gt;/g, '>').replace(/&amp;/g, '&').replace(/&quot;/g, '"').replace(/&#x27;/g, "'")
    .replace(/[​⁣]/g, '');
  return txt;
}
const norm = (t) => t.replace(/⏎/g, ' ').replace(/\s+/g, ' ').trim();
const B = JSON.parse(fs.readFileSync(process.argv[2])), A = JSON.parse(fs.readFileSync(process.argv[3]));
const KINDS = process.argv[4] ? JSON.parse(fs.readFileSync(process.argv[4])) : {};
let same = 0, spaceonly = 0, diff = 0, unexpected = 0, lines = [];
for (const id of Object.keys(A)) {
  for (let c = 0; c < 2; c++) {
    const b = B[id][c], a = A[id][c];
    if (b == null || a == null || b === a) continue;
    for (const mode of ['legacy']) {
      const vb = visible(b, mode), va = visible(a, mode);
      const nb = norm(vb), na = norm(va);
      if (nb === na) { same++; lines.push(`SAME ${id} [${c ? 'latex' : 'text'}]`); continue; }
      if (nb.replace(/\s+/g, '') === na.replace(/\s+/g, '')) { spaceonly++; lines.push(`SPACE-ONLY ${id} [${c ? 'latex' : 'text'}] (${KINDS[id] || '?'})`); continue; }
      diff++;
      if (KINDS[id] === 'layout' || KINDS[id] === 'merge') { unexpected++; lines.push(`UNEXPECTED(${KINDS[id]}) ${id}`); }
      let i = 0; while (i < nb.length && i < na.length && nb[i] === na[i]) i++;
      lines.push(`DIFF ${id} [${c ? 'latex' : 'text'}] @${i}: «${nb.slice(Math.max(0, i - 25), i + 70)}» -> «${na.slice(Math.max(0, i - 25), i + 70)}»`);
    }
  }
}
console.log(lines.join('\n'));
console.log(`identical visible text: ${same}; differs only in spaces/line breaks: ${spaceonly}; content changed: ${diff}; unexpected content change in layout/merge kinds: ${unexpected}`);
