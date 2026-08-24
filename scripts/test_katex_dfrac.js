const katex = require('/Users/arslan/Desktop/ALGO/algo-front/node_modules/katex');

const text1 = "Ты ошибся, когда подставил $t = \\frac{1}{2}$ в функцию $h(t) = t + \\frac{1}{t}$. Ты, вероятно, посчитал, что $\\frac{1}{t}$ при $t = \\frac{1}{2}$ равно 2, но забыл прибавить само значение $t$. Правильно: $h\\left(\\frac{1}{2}\\right) = \\frac{1}{2} + \\frac{1}{1/2} = \\frac{1}{2} + 2 = \\frac{5}{2}$, а не просто 2.";

// In MathRenderer, if we replace inline \frac with \dfrac:
const enhanced = text1.replace(/\\frac(?![a-zA-Z])/g, "\\dfrac");
console.log("Original text sample:", text1.slice(0, 80));
console.log("Enhanced text sample:", enhanced.slice(0, 80));

const htmlOrig = katex.renderToString("h\\left(\\frac{1}{2}\\right) = \\frac{1}{2} + \\frac{1}{1/2} = \\frac{1}{2} + 2 = \\frac{5}{2}", { displayMode: false, strict: 'ignore' });
const htmlDfrac = katex.renderToString("h\\left(\\dfrac{1}{2}\\right) = \\dfrac{1}{2} + \\dfrac{1}{1/2} = \\dfrac{1}{2} + 2 = \\dfrac{5}{2}", { displayMode: false, strict: 'ignore' });

console.log("Original has dfrac class:", htmlOrig.includes("dfrac"));
console.log("Dfrac has dfrac class:   ", htmlDfrac.includes("dfrac"));
