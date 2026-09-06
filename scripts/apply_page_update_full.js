const fs = require('fs');

const filePath = '/Users/arslan/Desktop/ALGO/algo-front/src/app/admin/diagnostics/[id]/report/page.tsx';
let content = fs.readFileSync(filePath, 'utf8');

const newFunctions = `// A robust comparison key for math & text options: normalizes LaTeX macros, empty sets, and Unicode symbols
// (\\dfrac, \\frac, \\sqrt, \\left, \\right, \\emptyset, commas, $, spaces, minuses, \\infty, \\leq, \\geq, \\neq, \\in, \\cup, \\cap, \\mathbb, \\approx, \\Delta, \\setminus, ^{...}, _{...})
// to reliably highlight the student's chosen answer and the correct answer without false fallback banners.
function canonicalAnswerKey(value: string | null | undefined): string {
  let s = (value || "").trim();
  if (!s) return "";
  // 1. Strip outer and inline LaTeX math delimiters
  s = s.replace(/\\$\\$/g, "").replace(/\\$/g, "");
  // 2. Normalize mathematical minuses and dashes (U+2212, U+2013, U+2014) to standard hyphen
  s = s.replace(/\\u2212/g, "-").replace(/\\u2013/g, "-").replace(/\\u2014/g, "-");
  
  // 3. Strip structural modifiers FIRST (\\left, \\right, \\displaystyle, \\limits, \\text{...})
  s = s.replace(/\\\\?(?:left|right|displaystyle|limits)\\b/g, "");
  s = s.replace(/\\\\?text\\s*\\{([^{}]*)\\}/g, "$1");
  
  // 4. Empty set & no solution normalization
  s = s.replace(/\\\\?(?:emptyset|varnothing|empty)\\b|[∅⌀Ø]/g, "emptyset");
  s = s.replace(/нет\\s*(?:действительных\\s*)?(?:корней|решений)|(?:корней|решений)\\s*нет/gi, "emptyset");
  
  // 5. Simplify single-level exponents and subscripts before fractions to avoid nested braces
  // e.g. e^{x} -> e^x, x_{0} -> x_0, a^{2} -> a^2
  while (/\\^\\{([^{}]+)\\}/.test(s)) {
    s = s.replace(/\\^\\{([^{}]+)\\}/g, "^$1");
  }
  while (/_\\{([^{}]+)\\}/.test(s)) {
    s = s.replace(/_\\{([^{}]+)\\}/g, "_$1");
  }
  
  // 6. Roots: \\sqrt{x} -> sqrt(x), \\sqrt[n]{x} -> (x)^(1/n)
  while (/\\\\?sqrt\\s*\\{([^{}]+)\\}/.test(s)) {
    s = s.replace(/\\\\?sqrt\\s*\\{([^{}]+)\\}/g, "sqrt($1)");
  }
  s = s.replace(/\\\\?sqrt/g, "sqrt").replace(/√/g, "sqrt");
  
  // 7. Fractions: recursively resolve \\frac{num}{den} and \\dfrac{num}{den}
  while (/\\\\?(?:dfrac|frac)\\s*\\{([^{}]+)\\}\\s*\\{([^{}]+)\\}/.test(s)) {
    s = s.replace(/\\\\?(?:dfrac|frac)\\s*\\{([^{}]+)\\}\\s*\\{([^{}]+)\\}/g, "($1)/($2)");
  }
  s = s.replace(/\\\\?(?:dfrac|frac)\\b/g, "/");
  
  // 8. Inequalities, approximations, set operations, and relations
  s = s.replace(/\\\\?(?:approx|thickapprox|sim|simeq)\\b|≈|~/g, "≈");
  s = s.replace(/\\\\?(?:Delta|delta)\\b|Δ|δ/g, "Δ");
  s = s.replace(/\\\\?(?:prime)\\b|'/g, "'");
  s = s.replace(/\\\\?(?:leq|le)\\b|≤/g, "<=");
  s = s.replace(/\\\\?(?:geq|ge)\\b|≥/g, ">=");
  s = s.replace(/\\\\?(?:neq|ne)\\b|≠/g, "!=");
  s = s.replace(/\\\\?notin\\b|∉/g, "!in");
  s = s.replace(/\\\\?(?:setminus|backslash)\\b|\\\\/g, "\\\\");
  s = s.replace(/\\\\?in\\b|∈/g, "in");
  s = s.replace(/\\\\?infty\\b|∞/g, "inf");
  s = s.replace(/\\\\?cup\\b|∪/g, "U");
  s = s.replace(/\\\\?cap\\b|∩/g, "cap");
  s = s.replace(/\\\\?(?:cdot|times)\\b|\\*|·/g, "");
  s = s.replace(/\\\\?mathbb\\{R\\}|\\\\?mathbb\\s+R|ℝ/g, "R");
  s = s.replace(/\\\\?mathbb\\{Z\\}|\\\\?mathbb\\s+Z|ℤ/g, "Z");
  s = s.replace(/\\\\?mathbb\\{Q\\}|\\\\?mathbb\\s+Q|ℚ/g, "Q");
  s = s.replace(/\\\\?mathbb\\{N\\}|\\\\?mathbb\\s+N|ℕ/g, "N");
  s = s.replace(/\\\\?pi\\b|π/g, "pi");
  s = s.replace(/\\^?\\\\?circ\\b|°/g, "");
  s = s.replace(/\\{,\\}/g, ".").replace(/,/g, ".");
  
  // 9. Strip remaining latex command backslashes, curly braces, and whitespace
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
  // If only difference is extra outer/inner parentheses around terms
  const stripParens = (str: string) => str.replace(/[()]/g, "");
  if (stripParens(ka) === stripParens(kb)) return true;
  return false;
}

function matchesOption(answer: string | null | undefined, opt: string, latexOpt: string, index: number): boolean {
  if (!answer) return false;
  const ans = answer.trim();
  if (!ans) return false;
  
  // 1. Direct / canonical equivalence
  if (areAnswersEquivalent(ans, opt) || areAnswersEquivalent(ans, latexOpt)) {
    return true;
  }
  
  const canAns = canonicalAnswerKey(ans);
  
  // 2. Letter matches ("A", "B", "C", "D" or "а", "б", "в", "г")
  const enLetter = String.fromCharCode(65 + index).toLowerCase();
  const ruLetter = ["а", "б", "в", "г", "д", "е"][index] || "";
  if (canAns === enLetter || canAns === ruLetter) {
    return true;
  }

  // 3. Explicit index patterns ("option_0", "choice_1", "opt_2", "#0")
  const explicitIndexMatch = ans.match(/^(?:option|choice|opt|ans|idx|#)[_\\s-]*([0-9]+)$/i);
  if (explicitIndexMatch && parseInt(explicitIndexMatch[1], 10) === index) {
    return true;
  }
  
  return false;
}`;

// Replace the functions section
const canonStart = content.indexOf('// A robust comparison key for math');
const canonEnd = content.indexOf('// ─── Sub-components');
if (canonStart !== -1 && canonEnd !== -1) {
  content = content.substring(0, canonStart) + newFunctions + "\n\n" + content.substring(canonEnd);
} else {
  console.error("Could not find canon start or end!");
  process.exit(1);
}

// Update deduplication in page.tsx
content = content.replace(
  'const key = canonicalAnswerKey(opt);',
  'const key = canonicalAnswerKey(opt) || (opt || "").trim().toLowerCase();'
);

fs.writeFileSync(filePath, content, 'utf8');
console.log("Successfully updated page.tsx with empty set, letter matching, and robust deduplication!");
