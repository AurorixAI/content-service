const fs = require('fs');
const { canonicalAnswerKey, areAnswersEquivalent } = require('./test_all_robust.js');

const raw = fs.readFileSync('/tmp/mcq_audit.json', 'utf8');
const errors = JSON.parse(raw);

let mcqTotal = 0;
let mcqMatched = 0;
let unmatched = [];

for (const err of errors) {
  const sa = err.student_answer;
  const options = err.options || [];
  const optionsLatex = err.options_latex || [];
  if (options.length === 0 && optionsLatex.length === 0) continue;
  
  mcqTotal++;
  let foundStudent = false;
  for (let i = 0; i < Math.max(options.length, optionsLatex.length); i++) {
    const opt = options[i] || "";
    const latexOpt = optionsLatex[i] || "";
    const indexStr = String(i);
    const letterStr = String.fromCharCode(65 + i).toLowerCase();
    const ruLetterStr = ["а", "б", "в", "г", "д", "е"][i] || "";
    
    if (
      areAnswersEquivalent(sa, opt) ||
      areAnswersEquivalent(sa, latexOpt) ||
      canonicalAnswerKey(sa) === indexStr ||
      canonicalAnswerKey(sa) === letterStr ||
      canonicalAnswerKey(sa) === ruLetterStr
    ) {
      foundStudent = true;
      break;
    }
  }
  
  if (foundStudent) {
    mcqMatched++;
  } else {
    unmatched.push({
      task_id: err.task_id,
      sa: sa,
      options: options,
      optionsLatex: optionsLatex
    });
  }
}

console.log(`MCQ Matched: ${mcqMatched} / ${mcqTotal} (${(mcqMatched / mcqTotal * 100).toFixed(1)}%)`);
if (unmatched.length > 0) {
  console.log(`Unmatched count: ${unmatched.length}. First 5:`, JSON.stringify(unmatched.slice(0, 5), null, 2));
}
