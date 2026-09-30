# -*- coding: utf-8 -*-
"""Restore spec for the key-not-in-options tasks (see knio_cfg.py). Options are rebuilt as [key] + distractor values,
so the stored options, the key and distractor_meta agree and the services show exactly one correct option."""
import copy, json, importlib.util, psycopg2

spec_mod = importlib.util.spec_from_file_location("cfg", "/audit/knio_cfg.py")
cfg = importlib.util.module_from_spec(spec_mod); spec_mod.loader.exec_module(cfg)
ids = json.load(open("/audit/knio_ids.json"))["n5"]
c = psycopg2.connect("postgresql://algo:algo_password@algo-content-db:5432/algo_content").cursor()


def dm(v, why):
    return {"value": v, "value_latex": v, "error_type": "misprint_fix_review", "plausibility": 0.6,
            "error_logic": why, "error_logic_latex": why, "explanation": why, "explanation_latex": why}


out = {}
for tid in ids:
    c.execute("SELECT correct_answer, correct_answer_latex, distractor_meta, question_text, question_latex FROM tasks_master WHERE id=%s AND is_active", (tid,))
    r = c.fetchone(); assert r, tid
    ca, cal, old, qt, ql = r
    e = cfg.C.get(tid, {})
    ds = [copy.deepcopy(d) for d in old if isinstance(d, dict)]
    assert len(ds) == len(old) == 3, tid
    if "d" in e:
        ds = [dm(v, w) for v, w in e["d"]]
    for i, v in e.get("dval", {}).items():
        ds[i]["value"] = v; ds[i]["value_latex"] = v
    for i, (v, w) in e.get("dnew", {}).items():
        ds[i] = dm(v, w)
    ds = [d for i, d in enumerate(ds) if i not in e.get("drop", [])]
    assert len(ds) >= 2, tid
    for d in ds:
        for f in ("value", "value_latex", "error_logic", "error_logic_latex", "explanation", "explanation_latex"):
            if isinstance(d.get(f), str):
                assert all(ch not in d[f] for ch in "\x07\r\x0c\t\x08"), (tid, f)
    f = {}
    if "k" in e:
        ca = cal = e["k"]; f["correct_answer"] = ca; f["correct_answer_latex"] = cal
    if "q" in e:
        assert all(ch not in e["q"] for ch in "\x07\r\x0c\t\x08"), tid
        f["question_text"] = e["q"]; f["question_latex"] = e["q"]
    if ds != old:
        f["distractor_meta"] = ds
    f["answer_options"] = [ca] + [d.get("value") for d in ds]
    f["answer_options_latex"] = [cal or ca] + [d.get("value_latex") or d.get("value") for d in ds]
    assert len(set(f["answer_options"])) == len(f["answer_options"]), tid
    why = ("варианты ответа приведены в соответствие с ключом: сохранённые варианты были построены для прежнего (неверного или искажённого) ключа, "
           "и сервисы показывали 5 вариантов; теперь варианты = ключ + неверные варианты из distractor_meta; ключ проверен вручную по учебнику и вычислением")
    for tag, key in (("условие восстановлено", "qwhy"), ("ключ", "kwhy"), ("закрыт неверный вариант", "dwhy")):
        if e.get(key):
            why += f"; {tag}: {e[key]}"
    s = {"why": why, "source": "Нелин 11 (2011) / Макарычев 9: ручная сверка 25.09", "fields": f}
    if "k" in e:
        s["expect_text"] = ca
    else:
        s["key_unchanged"] = True
    out[tid] = s
json.dump(out, open("/audit/restore_J_knio.json", "w"), ensure_ascii=False, indent=1)
print("tasks:", len(out), "| key changes:", sum("expect_text" in s for s in out.values()),
      "| statement changes:", sum("question_text" in s["fields"] for s in out.values()),
      "| distractor changes:", sum("distractor_meta" in s["fields"] for s in out.values()))
