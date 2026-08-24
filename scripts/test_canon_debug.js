function canonicalAnswerKey(value) {
  let s = (value || "").trim();
  if (!s) return "";
  s = s.replace(/\$\$/g, "").replace(/\$/g, "");
  s = s.replace(/\u2212/g, "-").replace(/\u2013/g, "-").replace(/\u2014/g, "-");
  
  // Fractions: convert \frac{num}{den} to num/den, \dfrac{num}{den} to num/den
  s = s.replace(/\\dfrac\s*\{([^{}]+)\}\s*\{([^{}]+)\}/g, "($1)/($2)");
  s = s.replace(/\\frac\s*\{([^{}]+)\}\s*\{([^{}]+)\}/g, "($1)/($2)");
  s = s.replace(/\\dfrac/g, "/").replace(/\\frac/g, "/");
  s = s.replace(/\\sqrt/g, "sqrt").replace(/√/g, "sqrt");
  
  s = s.replace(/\\leq/g, "<=").replace(/\\le/g, "<=").replace(/≤/g, "<=");
  s = s.replace(/\\geq/g, ">=").replace(/\\ge/g, ">=").replace(/≥/g, ">=");
  s = s.replace(/\\neq/g, "!=").replace(/\\ne/g, "!=").replace(/≠/g, "!=");
  s = s.replace(/\\notin/g, "!in").replace(/∉/g, "!in");
  s = s.replace(/\\in/g, "in").replace(/∈/g, "in");
  s = s.replace(/\\infty/g, "inf").replace(/∞/g, "inf");
  s = s.replace(/\\cup/g, "U").replace(/∪/g, "U");
  s = s.replace(/\\cap/g, "cap").replace(/∩/g, "cap");
  s = s.replace(/\\cdot/g, "").replace(/\\times/g, "").replace(/\*/g, "").replace(/·/g, "");
  s = s.replace(/\\left/g, "").replace(/\\right/g, "");
  s = s.replace(/\\mathbb\{R\}|\\mathbb\s+R|ℝ/g, "R");
  s = s.replace(/\\mathbb\{Z\}|\\mathbb\s+Z|ℤ/g, "Z");
  s = s.replace(/\\mathbb\{Q\}|\\mathbb\s+Q|ℚ/g, "Q");
  s = s.replace(/\\mathbb\{N\}|\\mathbb\s+N|ℕ/g, "N");
  s = s.replace(/\\pi/g, "pi").replace(/π/g, "pi");
  s = s.replace(/\^\\circ|\\circ|°/g, "");
  s = s.replace(/\{,\}/g, ".").replace(/,/g, ".");
  
  s = s.replace(/\\[a-zA-Z]+/g, "");
  s = s.replace(/[{}]/g, "");
  s = s.replace(/\s+/g, "");
  return s.toLowerCase();
}

function areAnswersEquivalent(a, b) {
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
