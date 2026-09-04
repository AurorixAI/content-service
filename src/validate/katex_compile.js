// katex_compile.js — батч-компиляция формул через KaTeX.
//
// Читает с stdin JSON-массив строк LaTeX, пытается отрендерить каждую с
// throwOnError:true и печатает в stdout JSON-массив объектов {ok, error}.
// Порядок сохраняется. Один процесс на батч — вызывается из src/validate/katex.py.
'use strict';

const katex = require('katex');

function readStdin() {
  return new Promise((resolve, reject) => {
    let buf = '';
    process.stdin.setEncoding('utf8');
    process.stdin.on('data', (c) => (buf += c));
    process.stdin.on('end', () => resolve(buf));
    process.stdin.on('error', reject);
  });
}

(async () => {
  let formulas;
  try {
    formulas = JSON.parse(await readStdin());
    if (!Array.isArray(formulas)) throw new Error('expected JSON array');
  } catch (e) {
    process.stderr.write('katex_compile: bad input: ' + e.message + '\n');
    process.exit(2);
  }
  const out = formulas.map((f) => {
    try {
      katex.renderToString(String(f), { throwOnError: true, displayMode: false });
      return { ok: true, error: null };
    } catch (e) {
      return { ok: false, error: (e && e.message) ? e.message : String(e) };
    }
  });
  process.stdout.write(JSON.stringify(out));
})();
