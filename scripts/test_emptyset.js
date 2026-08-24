const fs = require('fs');

const pageContent = fs.readFileSync('/Users/arslan/Desktop/ALGO/algo-front/src/app/admin/diagnostics/[id]/report/page.tsx', 'utf8');

let evalCode = pageContent.slice(
  pageContent.indexOf('function canonicalAnswerKey'),
  pageContent.indexOf('// ─── Sub-components')
);

evalCode = evalCode.replace(/: string \| null \| undefined/g, "")
                   .replace(/: string/g, "")
                   .replace(/: boolean/g, "")
                   .replace(/: number/g, "");

const vm = require('vm');
const context = { console };
vm.createContext(context);
vm.runInContext(evalCode, context);

const optEmpty = "$\\emptyset$";
console.log("canonicalAnswerKey('$\\emptyset$'):", repr(context.canonicalAnswerKey(optEmpty)));

function repr(s) { return JSON.stringify(s); }
