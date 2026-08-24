let s = "$(-\\infty; 3]$";
console.log("0:", s);
s = s.replace(/\$\$/g, "").replace(/\$/g, "");
console.log("1 after $:", s);
console.log("1 char codes:", [s.charCodeAt(0), s.charCodeAt(1), s.charCodeAt(2), s.charCodeAt(3)]);
s = s.replace(/\\infty/g, "inf");
console.log("2 after infty:", s);
