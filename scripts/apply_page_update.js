const fs = require('fs');

const filePath = '/Users/arslan/Desktop/ALGO/algo-front/src/app/admin/diagnostics/[id]/report/page.tsx';
let content = fs.readFileSync(filePath, 'utf8');

const newFunctions = `// A robust comparison key for math & text options: normalizes LaTeX macros and Unicode symbols
// (\\dfrac, \\frac, \\left, \\right, commas, $, spaces, minuses, \\infty, \\leq, \\geq, \\neq, \\in, \\cup, \\cap, \\mathbb)
// to reliably highlight the student's chosen answer and the correct answer.
function canonicalAnswerKey(value: string | null | undefined): string {
  let s = (value || "").trim();
  if (!s) return "";
  // Strip outer and inline LaTeX math delimiters
  s = s.replace(/\\$\\$/g, "").replace(/\\$/g, "");
  // Normalize mathematical minuses and dashes (U+2212, U+2013, U+2014) to standard hyphen
  s = s.replace(/\\u2212/g, "-").replace(/\\u2013/g, "-").replace(/\\u2014/g, "-");
  
  // Fractions: convert \\frac{num}{den} to (num)/(den), \\dfrac{num}{den} to (num)/(den)
  s = s.replace(/\\\\?dfrac\\s*\\{([^{}]+)\\}\\s*\\{([^{}]+)\\}/g, "($1)/($2)");
  s = s.replace(/\\\\?frac\\s*\\{([^{}]+)\\}\\s*\\{([^{}]+)\\}/g, "($1)/($2)");
  s = s.replace(/\\\\?(dfrac|frac)/g, "/");
  s = s.replace(/\\\\?sqrt/g, "sqrt").replace(/√/g, "sqrt");
  
  // Normalize inequalities, relations, and sets
  s = s.replace(/\\\\?le(q)?/g, "<=").replace(/≤/g, "<=");
  s = s.replace(/\\\\?ge(q)?/g, ">=").replace(/≥/g, ">=");
  s = s.replace(/\\\\?ne(q)?/g, "!=").replace(/≠/g, "!=");
  s = s.replace(/\\\\?notin/g, "!in").replace(/∉/g, "!in");
  s = s.replace(/\\\\?in/g, "in").replace(/∈/g, "in");
  s = s.replace(/\\\\?infty/g, "inf").replace(/∞/g, "inf");
  s = s.replace(/\\\\?cup/g, "U").replace(/∪/g, "U");
  s = s.replace(/\\\\?cap/g, "cap").replace(/∩/g, "cap");
  s = s.replace(/\\\\?(cdot|times)|\\*|·/g, "");
  s = s.replace(/\\\\?(left|right)/g, "");
  s = s.replace(/\\\\?mathbb\\{R\\}|\\\\?mathbb\\s+R|ℝ/g, "R");
  s = s.replace(/\\\\?mathbb\\{Z\\}|\\\\?mathbb\\s+Z|ℤ/g, "Z");
  s = s.replace(/\\\\?mathbb\\{Q\\}|\\\\?mathbb\\s+Q|ℚ/g, "Q");
  s = s.replace(/\\\\?mathbb\\{N\\}|\\\\?mathbb\\s+N|ℕ/g, "N");
  s = s.replace(/\\\\?pi/g, "pi").replace(/π/g, "pi");
  s = s.replace(/\\^?\\\\?circ|°/g, "");
  s = s.replace(/\\{,\\}/g, ".").replace(/,/g, ".");
  
  // Strip remaining latex command backslashes, curly braces, and whitespace
  s = s.replace(/\\\\[a-zA-Z]+/g, "");
  s = s.replace(/[{}]/g, "");
  s = s.replace(/\\s+/g, "");
  return s.toLowerCase();
}

function areAnswersEquivalent(a: string | null | undefined, b: string | null | undefined): boolean {
  if (!a || !b) return false;
  const ka = canonicalAnswerKey(a);
  const kb = canonicalAnswerKey(b);
  if (!ka || !kb) return false;
  if (ka === kb) return true;
  // If only difference is extra outer/inner parentheses around terms e.g. (8)/5 vs 8/5 or ((a-2)^2+4)/5 vs (a-2)^2+4/5
  const stripParens = (str: string) => str.replace(/[()]/g, "");
  if (stripParens(ka) === stripParens(kb)) return true;
  return false;
}

function matchesOption(answer: string | null | undefined, opt: string, latexOpt: string, index: number): boolean {
  if (!answer) return false;
  const ans = answer.trim();
  if (!ans) return false;
  
  // Direct / canonical equivalence
  if (areAnswersEquivalent(ans, opt) || areAnswersEquivalent(ans, latexOpt)) {
    return true;
  }
  
  // Index matches ("0", "1", "2", "3")
  const canAns = canonicalAnswerKey(ans);
  if (canAns === String(index)) {
    return true;
  }
  
  // Letter matches ("A", "B", "C", "D" or "а", "б", "в", "г")
  const enLetter = String.fromCharCode(65 + index).toLowerCase();
  const ruLetter = ["а", "б", "в", "г", "д", "е"][index] || "";
  if (canAns === enLetter || canAns === ruLetter) {
    return true;
  }
  
  return false;
}`;

// 1. Replace canonicalAnswerKey function
const canonStart = content.indexOf('// A robust comparison key for math');
const canonEnd = content.indexOf('// ─── Sub-components');
if (canonStart !== -1 && canonEnd !== -1) {
  content = content.substring(0, canonStart) + newFunctions + "\n\n" + content.substring(canonEnd);
} else {
  console.error("Could not find canon start or end!");
  process.exit(1);
}

// 2. Replace MCQ section
const mcqPatternStart = content.indexOf('{/* MCQ Options (if applicable) */}');
const mcqPatternEnd = content.indexOf('{/* Text answer comparison (non-MCQ) */}');

const newMcqBlock = `{/* MCQ Options (if applicable) */}
                          {hasMcqOptions && (() => {
                            const optionsList = err.answer_options || [];
                            const optionsLatex = err.answer_options_latex || [];
                            const hasLongOptions = optionsList.some(opt => (opt || "").length > 60);
                            const hasMatchedStudentOpt = optionsList.some((opt, oi) => matchesOption(err.student_answer, opt, optionsLatex[oi] || opt, oi));

                            return (
                              <div className="space-y-3">
                                <div className={\`grid gap-3 \${hasLongOptions ? "grid-cols-1" : "grid-cols-1 sm:grid-cols-2"}\`}>
                                  {optionsList.map((opt, oi) => {
                                    const latexOpt = optionsLatex[oi] || opt;
                                    const isCorrect = matchesOption(err.correct_answer, opt, latexOpt, oi);
                                    const isStudentAnswer = matchesOption(err.student_answer, opt, latexOpt, oi);
                                    return (
                                      <div key={oi} className={\`flex items-start gap-3 p-4 rounded-2xl border transition-all \${
                                        isCorrect
                                          ? "bg-emerald-50/70 border-emerald-200/90 shadow-2xs"
                                          : isStudentAnswer && !isCorrect
                                            ? "bg-white border-rose-200/90 shadow-2xs"
                                            : "bg-white border-slate-200/70 hover:border-slate-300"
                                      }\`}>
                                        <span className={\`w-6 h-6 rounded-lg text-[11px] font-black flex items-center justify-center flex-shrink-0 mt-0.5 \${
                                          isCorrect ? "bg-emerald-600 text-white" :
                                          isStudentAnswer ? "bg-rose-500 text-white" :
                                          "bg-slate-100 text-slate-500"
                                        }\`}>{String.fromCharCode(65 + oi)}</span>
                                        <MathRenderer
                                          text={latexOpt}
                                          className={\`flex-1 min-w-0 text-[14px] leading-relaxed break-words \${
                                            isCorrect ? "font-medium text-emerald-950" :
                                            isStudentAnswer && !isCorrect ? "font-medium text-rose-950" :
                                            "font-normal text-slate-700"
                                          }\`}
                                        />
                                        {isCorrect && <CheckCircle2 className="w-4 h-4 text-emerald-600 flex-shrink-0 mt-0.5" />}
                                        {isStudentAnswer && !isCorrect && <XCircle className="w-4 h-4 text-rose-400 flex-shrink-0 mt-0.5" />}
                                      </div>
                                    );
                                  })}
                                </div>
                                {!hasMatchedStudentOpt && err.student_answer && !["idk", "__wrong__", "test"].includes(err.student_answer.trim().toLowerCase()) && (
                                  <div className="flex items-center gap-2 px-4 py-2.5 rounded-xl bg-rose-50/70 border border-rose-200/80 text-xs font-medium text-rose-950">
                                    <XCircle className="w-4 h-4 text-rose-500 flex-shrink-0" />
                                    <span className="font-semibold text-rose-700">Введённый ответ ученика:</span>
                                    <MathRenderer text={err.student_answer_latex || err.student_answer} className="font-medium" />
                                  </div>
                                )}
                              </div>
                            );
                          })()}

                          `;

if (mcqPatternStart !== -1 && mcqPatternEnd !== -1) {
  content = content.substring(0, mcqPatternStart) + newMcqBlock + content.substring(mcqPatternEnd);
} else {
  console.error("Could not find mcq block start or end!");
  process.exit(1);
}

fs.writeFileSync(filePath, content, 'utf8');
console.log("Successfully updated page.tsx!");
