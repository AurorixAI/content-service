import json, re
OP = r"(?:[+\-−*/:=<>^·×]|\\cdot|\\times|\\le(?:q)?|\\ge(?:q)?|\\approx|\\ne(?:q)?|\\pm|\\div)"
def classify(o, s):
    if o["kind"]: return o["kind"], o["why"]
    a, b = o["start"], o["start"] + len(o["tok"])
    if re.match(r",\d", s[b:]) or re.search(r"\d,$", s[:a]):
        return None, None  # chain «1,2,3»: a sequence, not a decimal
    L = s[:a].rstrip(); R = s[b:].lstrip()
    L1 = re.sub(r"[-−]\s*$", "", L).rstrip()  # drop a unary minus of the number itself
    whole = re.search(r"[\(\[]\s*[-−]?\s*$", s[:a]) and re.match(r"\s*[\)\]]", s[b:])
    if not whole:
        if re.search(OP + r"$", L1) or re.match(OP, R) or re.match(r"[a-zA-Z]|\\(?:sqrt|dfrac|frac|pi|%)|\s*(?:см|мм|м|кг|г|км|л|ч|мин|с|руб|%)\b", R) or re.match(r"\\%", R):
            return "DEC", "operator/variable/unit next to number"
        if re.search(r"[\(\[]$", L1) and re.match(r"[+\-−*/:=<>^]|\\cdot", R):
            return "DEC", "arithmetic in brackets"
    else:
        outL = re.sub(r"[\(\[]\s*[-−]?\s*$", "", s[:a]).rstrip()
        outR = re.sub(r"^\s*[\)\]]", "", s[b:]).lstrip()
        if re.search(OP + r"$", outL) or re.match(r"\^|" + OP, outR):
            return "DEC", "bracketed number inside arithmetic"
    return None, None
