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

const correct_answer = "1";
const opt0 = "1";
const opt1 = "-3, -2";
const opt2 = "Корней нет";
const opt3 = "Все числа являются корнями";

console.log("=== Testing Task 1 ===");
console.log("opt0 match correct:", context.matchesOption(correct_answer, opt0, opt0, 0));
console.log("opt1 match correct:", context.matchesOption(correct_answer, opt1, opt1, 1));
console.log("opt2 match correct:", context.matchesOption(correct_answer, opt2, opt2, 2));
console.log("opt3 match correct:", context.matchesOption(correct_answer, opt3, opt3, 3));

console.log("\nCanonical keys:");
console.log("correct_answer key:", repr(context.canonicalAnswerKey(correct_answer)));
console.log("opt0 key:          ", repr(context.canonicalAnswerKey(opt0)));
console.log("opt1 key:          ", repr(context.canonicalAnswerKey(opt1)));

function repr(s) { return JSON.stringify(s); }
