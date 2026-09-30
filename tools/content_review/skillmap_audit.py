# Content-based audit of task→skill binding (label-noise detection via TF-IDF centroids, per grade).
import psycopg2, re, json, math
import numpy as np
from collections import Counter, defaultdict
c = psycopg2.connect("postgresql://algo:algo_password@algo-content-db:5432/algo_content").cursor()
c.execute("""SELECT k.id, k.name_ru, coalesce(k.description,''), coalesce(k.example_task,''), coalesce(k.assessed_ability,''), coalesce(k.formula,''),
                    p.id, coalesce(p.name_ru,''), gp.id, coalesce(gp.name_ru,'')
             FROM knowledge_hierarchy k LEFT JOIN knowledge_hierarchy p ON p.id=k.parent_id LEFT JOIN knowledge_hierarchy gp ON gp.id=p.parent_id
             WHERE k.is_active AND k.level='L4'""")
SK = {r[0]: dict(name=r[1], text=" ".join(r[1:6]) + " " + r[7] + " " + r[9], parent=r[6], pname=r[7], gparent=r[8], gname=r[9]) for r in c.fetchall()}
c.execute("SELECT id, skill_id, question_latex, correct_answer_latex FROM tasks_master WHERE is_active AND skill_id IS NOT NULL")
TASKS = c.fetchall()
STOP = set("найдит вычисл решит запиш данн котор котор. если какое каком числа число значен выраже уравне ответ равен равна равно получ".split())
def toks(s):
    s = (s or "").lower().replace("ё", "е")
    out = []
    for m in re.finditer(r"\\[a-z]+|[a-zа-я]{3,}|\^|%|°|\||<|>|≤|≥|\\le|\\ge|=|:", s):
        w = m.group()
        if w.startswith("\\"): out.append(w)
        elif re.match(r"[а-я]", w): 
            st = w[:5]
            if st not in STOP: out.append(st)
        elif re.match(r"[a-z]{3,}", w): out.append(w[:6])
        else: out.append("SYM" + w)
    return out
res = []
by_grade = defaultdict(list)
for t in TASKS: by_grade[t[1].split("_")[0]].append(t)
for g, tasks in by_grade.items():
    skills = sorted({t[1] for t in tasks} | {s for s in SK if s.startswith(g + "_")})
    sidx = {s: i for i, s in enumerate(skills)}
    docs = [Counter(toks((q or "") + " " + (k or ""))) for _, _, q, k in tasks]
    sdocs = [Counter(toks(SK[s]["text"])) for s in skills]
    df = Counter(w for d in docs for w in d)
    vocab = [w for w, n in df.most_common(6000) if n >= 2]
    vi = {w: i for i, w in enumerate(vocab)}; N = len(docs)
    idf = np.array([math.log(N / (1 + df[w])) + 1 for w in vocab], dtype=np.float32)
    def vec(d):
        v = np.zeros(len(vocab), dtype=np.float32)
        for w, n in d.items():
            if w in vi: v[vi[w]] = (1 + math.log(n))
        v *= idf; nrm = np.linalg.norm(v); return v / nrm if nrm else v
    X = np.stack([vec(d) for d in docs]); D = np.stack([vec(d) for d in sdocs])
    S = np.zeros((len(skills), len(vocab)), dtype=np.float32); cnt = np.zeros(len(skills))
    lab = np.array([sidx[t[1]] for t in tasks])
    np.add.at(S, lab, X); np.add.at(cnt, lab, 1)
    for i, t in enumerate(tasks):
        own = lab[i]
        cent = S.copy(); cent[own] -= X[i]
        cent = cent + 2.0 * D                                   # skill description as prior
        cent /= np.maximum(np.linalg.norm(cent, axis=1, keepdims=True), 1e-9)
        sims = cent @ X[i]
        best = int(np.argmax(sims)); s_own = float(sims[own])
        if best != own:
            b = skills[best]; o = skills[own]
            rel = "sibling" if SK.get(b, {}).get("parent") == SK.get(o, {}).get("parent") else ("same_L2" if SK.get(b, {}).get("gparent") == SK.get(o, {}).get("gparent") else "other_L2")
            rank = int((sims > s_own).sum())
            res.append(dict(id=t[0], own=o, best=b, s_own=round(s_own, 3), s_best=round(float(sims[best]), 3), rank=rank, rel=rel, q=" ".join((t[2] or "").split())[:160]))
json.dump(res, open("/audit/skillmap_candidates.json", "w"), ensure_ascii=False, indent=0)
print("tasks", len(TASKS), "best≠own", len(res))
print(Counter(r["rel"] for r in res))
strong = [r for r in res if r["rel"] == "other_L2" and r["rank"] >= 10 and r["s_best"] - r["s_own"] > 0.15]
print("strong (other L2, own rank≥10, margin>0.15):", len(strong), Counter(r["own"].split("_")[0] for r in strong))
