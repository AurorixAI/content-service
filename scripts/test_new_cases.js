const { canonicalAnswerKey, areAnswersEquivalent } = require('./test_user_screenshots.js');

// Screenshot 1: Setminus and \mathbb
const s1_student = "y = \\frac{2e^x + 1}{e^x - 1}, x \\in \\mathbb{R} \\setminus \\{0\\}";
const s1_optB = "$y = \\frac{2e^x + 1}{e^x - 1}, x \\in \\mathbb{R}\\setminus\\{0\\}$";
console.log("Screenshot 1 match:", areAnswersEquivalent(s1_student, s1_optB));
console.log("  s1_student key:", canonicalAnswerKey(s1_student));
console.log("  s1_optB key:   ", canonicalAnswerKey(s1_optB));

// Screenshot 2: \Delta / Δ, \approx / ≈, x_0
const s2_student = "f(x_0 + \\Delta x) \\approx f'(x_0) + f(x_0)\\Delta x";
const s2_student_unicode = "f(x_0 + Δx) ≈ f'(x_0) + f(x_0)Δx";
const s2_optB = "$f(x_0 + \\Delta x) \\approx f'(x_0) + f(x_0)\\Delta x$";
console.log("Screenshot 2 match (latex):  ", areAnswersEquivalent(s2_student, s2_optB));
console.log("Screenshot 2 match (unicode):", areAnswersEquivalent(s2_student_unicode, s2_optB));
console.log("  s2_student_u key:", canonicalAnswerKey(s2_student_unicode));
console.log("  s2_optB key:     ", canonicalAnswerKey(s2_optB));
