function containsRawLatex(s) {
  return /\\[a-zA-Z]+/.test(s) && !s.includes("$") && !s.includes("\\[") && !s.includes("\\(");
}

console.log("Raw '\\frac{1}{2}' has raw latex:", containsRawLatex("\\frac{1}{2}"));
console.log("Normal text has raw latex:      ", containsRawLatex("Корней нет"));
console.log("Math with $ has raw latex:      ", containsRawLatex("$\\frac{1}{2}$"));
