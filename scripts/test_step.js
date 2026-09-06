let s = "$(-\\infty; 3]$";
console.log("0 (len " + s.length + "):", s);

s = s.replace(/\$\$/g, "").replace(/\$/g, "");
console.log("1 after $:", s);

const before_infty = s;
s = s.replace(/\\infty/g, "inf");
console.log("2 after replace /\\\\infty/g:", s, "changed?", s !== before_infty);

const before_strip = s;
s = s.replace(/\\[a-zA-Z]+/g, "");
console.log("3 after strip /\\[a-zA-Z]+/:", s, "changed?", s !== before_strip);
