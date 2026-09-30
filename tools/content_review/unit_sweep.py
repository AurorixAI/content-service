import re, json, psycopg2
c = psycopg2.connect("postgresql://algo:algo_password@algo-content-db:5432/algo_content").cursor()
c.execute("SELECT id, correct_answer_latex, distractor_meta FROM tasks_master WHERE is_active AND distractor_meta IS NOT NULL")
U = r"(?:км/ч|м/мин|км|дм|см|мм|м|кг|г|т|ц|ч|мин|с|л|мл|га|а|сумов|сум|руб|лет|год|шт|°С|°C|С|C|рад)"
def n(s):
    s = str(s or ""); s = re.sub(r"\\(?:text|mathrm|operatorname)\{([^}]*)\}", r"\1", s)
    s = re.sub(r"\^\{?\\circ\}?|\\degree|°", "°", s); s = s.replace("{,}", ",").replace("\\,", "").replace("\\ ", "").replace("\\dfrac", "\\frac")
    s = re.sub(r"[\s$]", "", s); s = re.sub(r"(?<=\d) ?(?=\d{3}\b)", "", s)
    s = re.sub(r"(?<=[\d)])°?" + U + r"(?:\^\{?[23]\}?)?(?![А-Яа-яA-Za-z])", "", s); s = re.sub(r"(?<=\d)°", "", s)
    return s.rstrip(".;")
hits = []
for t, k, D in c.fetchall():
    nk = n(k)
    if not nk: continue
    for i, d in enumerate(D):
        v = d.get("value_latex") or d.get("value")
        if v and n(v) == nk: hits.append((t, i, k, v))
json.dump(hits, open("/audit/unit_hits.json", "w"), ensure_ascii=False)
print(len(hits))
for h in hits: print(h)
