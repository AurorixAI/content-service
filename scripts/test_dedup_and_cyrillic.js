const { canonicalAnswerKey, areAnswersEquivalent } = require('./test_user_screenshots.js');

// Test 1: Cyrillic text in KaTeX
const russianText = "Точки локального максимума и локального минимума функции.";
const isPureRussian = /^[а-яё\s.,!?:;«»()"-]+$/i.test(russianText.trim());
console.log("Is pure Russian text:", isPureRussian);

// Test 2: Options deduplication
const rawOptions = [
  "\\frac{x\\cos x - \\sin x}{x^2}",
  "\\cos\\frac{x}{1}",
  "\\cos\\frac{x}{x} - \\sin\\frac{x^2}{x}",
  "-\\cos\\frac{x^2}{x}",
  "\\frac{x\\cos x - \\sin x}{x^2}" // duplicate
];

const seen = new Set();
const deduped = [];
rawOptions.forEach((opt, idx) => {
  const k = canonicalAnswerKey(opt);
  if (!seen.has(k)) {
    seen.add(k);
    deduped.push({ opt, idx });
  }
});

console.log("Raw count:", rawOptions.length);
console.log("Deduped count:", deduped.length);
console.log("Deduped options:", deduped.map(d => d.opt));
