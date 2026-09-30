import psycopg2, re, json
from collections import defaultdict, Counter
c = psycopg2.connect("postgresql://algo:algo_password@algo-content-db:5432/algo_content").cursor()
c.execute("SELECT task_id, array_agg(figure_id ORDER BY order_idx) FROM task_figure_refs GROUP BY task_id"); FIG = {t: tuple(f) for t, f in c.fetchall()}
c.execute("""SELECT id, question_latex, question_text, correct_answer_latex, correct_answer, answer_type, split_part(source_reference,'::',1), split_part(source_reference,'::',2),
             question_image_url, skill_id, toc_id, jsonb_array_length(COALESCE(distractor_meta,'[]'::jsonb)), verification_status FROM tasks_master WHERE is_active""")
rows = c.fetchall()
def nq(q):
    q = (q or "").replace("\\dfrac", "\\frac").replace("\\tfrac", "\\frac").replace("{,}", ",").replace("\\left", "").replace("\\right", "").replace("\\,", "").replace("\\ ", "")
    q = re.sub(r"\\square|\[\?\]|▢|\\ast|(?<![\^_])\*|□", "#", q)
    q = q.replace("\\cdot", "·").replace("\\times", "×").replace("−", "-").replace("ё", "е").replace("Ё", "Е")
    q = re.sub(r"\$|\s", "", q)
    q = re.sub(r"(?<!\d)[.:;,!?]|[.:;,!?](?!\d)", "", q)
    q = re.sub(r"^(?:[а-яa-z]\)|\d+\))", "", q)          # leading item label only
    return q.rstrip(".;")
nk = lambda k: re.sub(r"\$|\s|\\,", "", (k or "")).replace("\\dfrac", "\\frac").replace("{,}", ",")
g = defaultdict(list)
for r in rows:
    t, ql, qt, kl, k, at, b, loc, img, sk, toc, nd, vs = r
    if len(nq(ql)) < 8: continue
    g[(b or "gen", nq(ql), nk(kl or k))].append(dict(id=t, loc=loc, img=img, fig=FIG.get(t), skill=sk, toc=toc, nd=nd, vs=vs, q=" ".join((ql or "").split())))
grp, rej = [], Counter()
for key, v in g.items():
    if len(v) < 2: continue
    if len({x["fig"] for x in v}) > 1: rej["different figures"] += 1; continue
    if len({x["img"] for x in v}) > 1: rej["different image"] += 1; continue
    if any(x["fig"] for x in v) or re.search(r"рис", key[1], re.I): rej["has figure / refers to figure (manual)"] += 1; grp.append(dict(book=key[0], k=key[2], items=v, flag="figure")); continue
    grp.append(dict(book=key[0], k=key[2], items=v, flag=""))
print("groups", len(grp), "extra", sum(len(x["items"]) - 1 for x in grp), "rejected/flagged", dict(rej))
print(Counter(x["book"][:8] for x in grp).most_common())
json.dump(grp, open("/audit/dup_strict.json", "w"), ensure_ascii=False, indent=0)
