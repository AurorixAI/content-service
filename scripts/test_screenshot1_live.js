function canonicalAnswerKey(value) {
  let s = (value || "").trim();
  if (!s) return "";
  // 1. Strip outer and inline LaTeX math delimiters
  s = s.replace(/\$\$/g, "").replace(/\$/g, "");
  // 2. Normalize mathematical minuses and dashes (U+2212, U+2013, U+2014) to standard hyphen
  s = s.replace(/\u2212/g, "-").replace(/\u2013/g, "-").replace(/\u2014/g, "-");
  
  // 3. Strip structural modifiers FIRST (\left, \right, \displaystyle, \limits, \text{...})
  s = s.replace(/\\?(?:left|right|displaystyle|limits)\b/g, "");
  s = s.replace(/\\?text\s*\{([^{}]*)\}/g, "$1");
  
  // 4. Simplify single-level exponents and subscripts before fractions to avoid nested braces
  // e.g. e^{x} -> e^x, x_{0} -> x_0, a^{2} -> a^2
  while (/\^\{([^{}]+)\}/.test(s)) {
    s = s.replace(/\^\{([^{}]+)\}/g, "^$1");
  }
  while (/_\Send\{([^{}]+)\}/.test(s) || /_\{([^{}]+)\}/.test(s)) {
    s = s.replace(/_\{([^{}]+)\}/g, "_$1");
  }
  
  // 5. Roots: \sqrt{x} -> sqrt(x), \sqrt[n]{x} -> (x)^(1/n)
  while (/\\?sqrt\s*\{([^{}]+)\}/.test(s)) {
    s = s.replace(/\\?sqrt\s*\{([^{}]+)\}/g, "sqrt($1)");
  }
  s = s.replace(/\\?sqrt/g, "sqrt").replace(/√/g, "sqrt");
  
  // 6. Fractions: recursively resolve \frac{num}{den} and \dfrac{num}{den}
  while (/\\?(?:dfrac|frac)\s*\{([^{}]+)\}\s*\{([^{}]+)\}/.test(s)) {
    s = s.replace(/\\?(?:dfrac|frac)\s*\{([^{}]+)\}\s*\{([^{}]+)\}/g, "($1)/($2)");
  }
  s = s.replace(/\\?(?:dfrac|frac)\b/g, "/");
  
  // 7. Inequalities, approximations, set operations, and relations
  s = s.replace(/\\?(?:approx|thickapprox|sim|simeq)\b|≈|~/g, "≈");
  s = s.replace(/\\?(?:Delta|delta)\b|Δ|δ/g, "Δ");
  s = s.replace(/\\?(?:prime)\b|'/g, "'");
  s = s.replace(/\\?(?:leq|le)\b|≤/g, "<=");
  s = s.replace(/\\?(?:geq|ge)\b|≥/g, ">=");
  s = s.replace(/\\?(?:neq|ne)\b|≠/g, "!=");
  s = s.replace(/\\?(?:notin)\b|∉/g, "!in");
  s = s.replace(/\\?(?:setminus|backslash)\b|\\/g, "\\");
  s = s.replace(/\\?(?:in)\b|∈/g, "in");
  s = s.replace(/\\?(?:infty)\b|∞/g, "inf");
  s = s.replace(/\\?(?:cup)\b|∪/g, "U");
  s = s.replace(/\\?(?:cap)\b|∩/g, "cap");
  s = s.replace(/\\?(?:cdot|times)\b|\*|·/g, "");
  s = s.replace(/\\?mathbb\{R\}|\\?mathbb\s+R|ℝ/g, "R");
  s = s.replace(/\\?mathbb\{Z\}|\\?mathbb\s+Z|ℤ/g, "Z");
  s = s.replace(/\\?mathbb\{Q\}|\\?mathbb\s+Q|ℚ/g, "Q");
  s = s.replace(/\\?mathbb\{N\}|\\?mathbb\s+N|ℕ/g, "N");
  s = s.replace(/\\?pi\b|π/g, "pi");
  s = s.replace(/\^?\\?circ\b|°/g, "");
  s = s.replace(/\{,\}/g, ".").replace(/,/g, ".");
  
  // 8. Strip remaining latex command backslashes, curly braces, and whitespace
  s = s.replace(/\\[a-zA-Z]+/g, "");
  s = s.replace(/[{}]/g, "");
  s = s.replace(/\s+/g, "");
  return s.toLowerCase();
}

function areAnswersEquivalent(a, b) {
  if (!a || !b) return false;
  const ka = canonicalAnswerKey(a);
  const kb = canonicalAnswerKey(b);
  if (!ka || !kb) return false;
  if (ka === kb) return true;
  // If only difference is extra outer/inner parentheses around terms
  const stripParens = (str) => str.replace(/[()]/g, "");
  if (stripParens(ka) === stripParens(kb)) return true;
  return false;
}

function matchesOption(answer, opt, latexOpt, index) {
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
}

const student_answer = '$y = \\dfrac{2e^{x} + 1}{e^{x} - 1}$, $x \\in \\mathbb{R} \\setminus \\{0\\}$';
const opt0 = '$y = \\dfrac{2e^{x} + 1}{e^{x} - 1}, x \\in (0; +\\infty)$';
const opt1 = '$y = \\dfrac{2e^x + 1}{e^x - 1}$, $x \\in \\mathbb{R} \\setminus \\{0\\}$';
const opt1_latex = '$y = \\dfrac{2e^x + 1}{e^x - 1}$, $x \\in \\mathbb{R} \\setminus \\{0\\}$';
const correct_answer = '$y = \\dfrac{2e^{x} + 1}{e^{x} - 1}, x \\in (0; +\\infty)$';

console.log("=== Testing Screenshot 1 ===");
const matchCorrect0 = matchesOption(correct_answer, opt0, opt0, 0);
const matchStudent0 = matchesOption(student_answer, opt0, opt0, 0);
const matchCorrect1 = matchesOption(correct_answer, opt1, opt1_latex, 1);
const matchStudent1 = matchesOption(student_answer, opt1, opt1_latex, 1);

console.log("Option A isCorrect:  ", matchCorrect0);
console.log("Option A isStudent:  ", matchStudent0);
console.log("Option B isCorrect:  ", matchCorrect1);
console.log("Option B isStudent:  ", matchStudent1);

console.log("\nCanonical keys:");
console.log("student_answer key:  ", canonicalAnswerKey(student_answer));
console.log("opt1 key:            ", canonicalAnswerKey(opt1));
