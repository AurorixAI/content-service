const katex = require('katex');

function isPureCyrillicText(s) {
  const trimmed = s.trim();
  return /[а-яА-ЯёЁ]/.test(trimmed) && !/\\[a-zA-Z]+/.test(trimmed) && !/[{}^_+=/*]/.test(trimmed);
}

function sanitizeCyrillicInMath(latex) {
  if (isPureCyrillicText(latex)) {
    return `\\text{${latex}}`;
  }
  return latex.replace(/(?<!\\text\{)(?<![a-zA-Z\\])([а-яА-ЯёЁ]+(?:\s+[а-яА-ЯёЁ]+)*)/g, (match) => {
    return `\\text{${match}}`;
  });
}

const input1 = "Точки локального максимума и локального минимума функции.";
console.log("Input 1 pure Cyrillic:", isPureCyrillicText(input1));
const rendered1 = katex.renderToString(sanitizeCyrillicInMath(input1), { throwOnError: false, displayMode: false });
console.log("Rendered with sanitize:", rendered1.includes("Точки") && rendered1.includes("локального"));

const input2 = "x \\in [0; 1] и y \\in [0; 1]";
console.log("Input 2 sanitized:", sanitizeCyrillicInMath(input2));
const rendered2 = katex.renderToString(sanitizeCyrillicInMath(input2), { throwOnError: false, displayMode: false });
console.log("Rendered 2 success:", !rendered2.includes("katex-error"));
