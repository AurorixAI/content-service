# -*- coding: utf-8 -*-
"""L6d (replaces L6c): distractors identical to the key.
(a) raw value equals the key -> removed; (b) only the display (value_latex) equals the key -> display rebuilt from the raw
value per the hand-reviewed map l6d_map.M, or removed where the map says None. Stored options are updated in parallel."""
import json, sys
sys.path.insert(0, "/audit")
from l6d_map import M
ns = {}; exec(open("/audit/l6c_build.py").read().split("c = psycopg2.connect")[0], ns); n = ns["n"]
import psycopg2
c = psycopg2.connect("postgresql://algo:algo_password@algo-content-db:5432/algo_content").cursor()
ids = sorted(set(json.load(open("/audit/restore_J_L6c.json"))) | set(M))
c.execute("SELECT id, correct_answer, correct_answer_latex, distractor_meta, answer_options, answer_options_latex FROM tasks_master WHERE id = ANY(%s) AND is_active", (ids,))
spec, used, few = {}, set(), []
for tid, ca, cal, dm, ao, aol in c.fetchall():
    ks = {n(ca), n(cal)}
    keep, drop_raw, fix, notes = [], set(), {}, []
    for d in dm:
        if not isinstance(d, dict):
            keep.append(d); continue
        rv = d.get("value")
        if rv is not None and n(rv) in ks:
            drop_raw.add(rv); notes.append(f"убран «{str(rv)[:50]}» (совпадает с ответом)"); continue
        if tid in M and rv in M[tid]:
            used.add((tid, rv)); new = M[tid][rv]
            if new is None:
                drop_raw.add(rv); notes.append(f"убран «{str(rv)[:50]}» (по смыслу совпадает с ответом или бессмыслен)"); continue
            keep.append(dict(d, value_latex=new)); fix[rv] = new; notes.append(f"отображение «{str(rv)[:40]}» исправлено: было как ключ, стало {new[:50]}"); continue
        keep.append(d)
    if not notes:
        continue
    f = {"distractor_meta": keep}
    if isinstance(ao, list) and ao:
        lat = aol if isinstance(aol, list) and len(aol) == len(ao) else None
        nao, naol = [], []
        for i, o in enumerate(ao):
            t = o.get("text") if isinstance(o, dict) else o
            if t in drop_raw: continue
            nao.append(o)
            if lat is not None:
                lo = lat[i]
                if t in fix:
                    lo = dict(lo, text=fix[t]) if isinstance(lo, dict) else fix[t]
                naol.append(lo)
        if nao != ao: f["answer_options"] = nao
        if lat is not None and naol != aol: f["answer_options_latex"] = naol
    if sum(isinstance(d, dict) for d in keep) < 2: few.append((tid, len(keep)))
    spec[tid] = {"why": "неверный вариант совпадал с правильным ответом (в сыром значении или в отображаемой LaTeX-колонке): " + "; ".join(notes),
                 "source": "L6d, ручная сверка 25.09", "fields": f, "key_unchanged": True}
missing = [(t, v) for t in M for v in M[t] if (t, v) not in used]
print("tasks:", len(spec), "| map entries unmatched:", missing)
print("left with <2 distractors:", few)
json.dump(spec, open("/audit/restore_J_L6d.json", "w"), ensure_ascii=False, indent=1)
