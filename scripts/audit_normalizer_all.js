const fs = require('fs');
const { canonicalAnswerKey, areAnswersEquivalent } = require('./test_all_robust.js');

const raw = fs.readFileSync('/tmp/mcq_audit.json', 'utf8');
const errors = JSON.parse(raw);

let matchedCount = 0;
let totalCount = errors.length;
let unmatched = [];

for (const err of errors) {
  const sa = err.student_answer;
  const ca = err.correct_answer;
  const options = err.options || [];
  const optionsLatex = err.options_latex || [];
  
  // Test if student answer matches any option
  let foundStudent = false;
  for (let i = 0; i < options.length; i++) {
    const opt = options[i];
    const latexOpt = optionsLatex[i] || "";
    const indexStr = String(i);
    const letterStr = String.fromCharCode(65 + i).toLowerCase(); // a, b, c, d
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
    matchedCount++;
  } else {
    unmatched.push({
      task_id: err.task_id,
      sa: sa,
      options: options,
      optionsLatex: optionsLatex
    });
  }
}

console.log(`Matched: ${matchedCount} / ${totalCount} (${(matchedCount/totalCount*100).toFixed(1)}%)`);
console.log(`Unmatched sample (first 5):`, JSON.stringify(unmatched.slice(0, 5), null, 2));
