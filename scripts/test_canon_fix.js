function canonicalAnswerKey(value) {
  let s = (value || "").trim();
  if (!s) return "";
  // Strip outer and inline LaTeX math delimiters
  s = s.replace(/\$\$/g, "").replace(/\$/g, "");
  // Normalize mathematical minuses and dashes (U+2212, U+2013, U+2014) to standard hyphen
  s = s.replace(/\u2212/g, "-").replace(/\u2013/g, "-").replace(/\u2014/g, "-");
  
  // Normalize fractions and roots: \\\\ matches literal backslash in JS regex
  // \dfrac{a}{b} -> (a)/(b)
  s = s.replace(/\\\\dfrac\s*\{([^{}]+)\}\s*\{([^{}]+)\}/g, "($1)/($2)");
  s = s.replace(/\\\\frac\s*\{([^{}]+)\}\s*\{([^{}]+)\}/g, "($1)/($2)");
  s = s.replace(/\\\\dfrac/g, "/").replace(/\\\\frac/g, "/");
  s = s.replace(/\\\\sqrt/g, "sqrt").replace(/√/g, "sqrt");
  
  // Normalize inequalities, relations, and sets
  s = s.replace(/\\\\leq/g, "<=").replace(/\\\\le/g, "<=").replace(/≤/g, "<=");
  s = s.replace(/\\\\geq/g, ">=").replace(/\\\\ge/g, ">=").replace(/≥/g, ">=");
  s = s.replace(/\\\\neq/g, "!=").replace(/\\\\ne/g, "!=").replace(/≠/g, "!=");
  s = s.replace(/\\\\notin/g, "!in").replace(/∉/g, "!in");
  s = s.replace(/\\\\in/g, "in").replace(/∈/g, "in");
  s = s.replace(/\\\\infty/g, "inf").replace(/∞/g, "inf");
  s = s.replace(/\\\\cup/g, "U").replace(/∪/g, "U");
  s = s.replace(/\\\\cap/g, "cap").replace(/∩/g, "cap");
  s = s.replace(/\\\\cdot/g, "").replace(/\\\\times/g, "").replace(/\*/g, "").replace(/·/g, "");
  s = s.replace(/\\\\left/g, "").replace(/\\\\right/g, "");
  s = s.replace(/\\\\mathbb\{R\}|\\\\mathbb\s+R|ℝ/g, "R");
  s = s.replace(/\\\\mathbb\{Z\}|\\\\mathbb\s+Z|ℤ/g, "Z");
  s = s.replace(/\\\\mathbb\{Q\}|\\\\mathbb\s+Q|ℚ/g, "Q");
  s = s.replace(/\\\\mathbb\{N\}|\\\\mathbb\s+N|ℕ/g, "N");
  s = s.replace(/\\\\pi/g, "pi").replace(/π/g, "pi");
  s = s.replace(/\^\\\\circ|\\\\circ|°/g, "");
  s = s.replace(/\{,\}/g, ".").replace(/,/g, ".");
  
  // Strip remaining latex command backslashes, curly braces, and whitespace
  s = s.replace(/\\\\[a-zA-Z]+/g, "");
  s = s.replace(/[{}]/g, "");
  s = s.replace(/\s+/g, "");
  return s.toLowerCase();
}

// Test 1: Task 8
const t8_sa = "D(f) = [0; +∞), E(f) = [2; +∞)";
const t8_optC = "$D(f) = [0; +\\infty), E(f) = [2; +\\infty)$";
console.log("Task 8 match:", canonicalAnswerKey(t8_sa) === canonicalAnswerKey(t8_optC));

// Test 2: Task 9
const t9_sa = "h(2)=8/5, h(-2)=-8/5, h(a)=(a^2+4)/5, h(-x)=(-x^2+4)/5, h(a-2)=((a-2)^2+4)/5, h(\\sqrt{x})=(x+4)/5";
const t9_optC = "$h(2) = \\frac{8}{5}, h(-2) = -\\frac{8}{5}, h(a) = \\frac{a^2+4}{5}, h(-x) = \\frac{(-x)^2+4}{5}, h(a-2) = \\frac{(a-2)^2+4}{5}, h(\\sqrt{x}) = \\frac{x+4}{5}$";
console.log("Task 9 match:", canonicalAnswerKey(t9_sa) === canonicalAnswerKey(t9_optC));

// Test 3: Task 3
const t3_sa = "(-∞; 3]";
const t3_optD = "$(-\\infty; 3]$";
console.log("Task 3 match:", canonicalAnswerKey(t3_sa) === canonicalAnswerKey(t3_optD));
