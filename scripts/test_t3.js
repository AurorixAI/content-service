const { canonicalAnswerKey, areAnswersEquivalent } = require('./test_canon_debug.js');
// Let's check t3
const t3_sa = "(-∞; 3]";
const t3_optD = "$(-\\infty; 3]$";
console.log("t3_sa key:", canonicalAnswerKey(t3_sa));
console.log("t3_optD key:", canonicalAnswerKey(t3_optD));
console.log("Equal?:", canonicalAnswerKey(t3_sa) === canonicalAnswerKey(t3_optD));
