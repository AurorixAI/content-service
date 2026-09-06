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
  
  // 4. Roots: \sqrt{x} -> sqrt(x), \sqrt[n]{x} -> (x)^(1/n)
  while (/\\?sqrt\s*\{([^{}]+)\}/.test(s)) {
    s = s.replace(/\\?sqrt\s*\{([^{}]+)\}/g, "sqrt($1)");
  }
  s = s.replace(/\\?sqrt/g, "sqrt").replace(/√/g, "sqrt");
  
  // 5. Fractions: recursively resolve \frac{num}{den} and \dfrac{num}{den}
  while (/\\?(?:dfrac|frac)\s*\{([^{}]+)\}\s*\{([^{}]+)\}/.test(s)) {
    s = s.replace(/\\?(?:dfrac|frac)\s*\{([^{}]+)\}\s*\{([^{}]+)\}/g, "($1)/($2)");
  }
  s = s.replace(/\\?(?:dfrac|frac)\b/g, "/");
  
  // 6. Inequalities, approximations, and relations
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
  
  // 7. Strip remaining latex command backslashes, curly braces, and whitespace
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

module.exports = { canonicalAnswerKey, areAnswersEquivalent };
