"""Build manifest n01-2026-10-08-w19-polish (grade 10-11 polish: residual moves + taxonomy structure). SELECT only.

Inputs (tools/content_review/audit/f1p):
  residual_1..6_out.jsonl   212 task moves (NULL only for tasks with toc_id; NOFIT keeps the current skill)
  structure_decisions.json  tier A, tier B (merge G10_S07_01 -> S07_02, 14 extra task moves, reparents,
                            12 L4 renames, L2/L3 renames of truncated names).
Not included on purpose: new L2 G10_T10 (and the P32/P34 reparent under it), G11_P04 rename (unverified guess),
G11_P45 rename, tier C (optional merges), the 20 cross-grade derivative moves.

Output: knowledge_update (renames, reparents), knowledge_deactivate (8 absorbed L4), repairs (skill_id only).
Usage (from content-service):
  CONTENT_REPAIR_DATABASE_URL=... python3 -m tools.content_review.build_w19_polish
Deterministic.
"""
from __future__ import annotations

import collections
import glob
import json
import os
import sys
from pathlib import Path

from sqlalchemy import create_engine, text

from tools.content_review import guarded_repair as gr

BATCH = "n01-source-repair-2026-10-08-w19-polish"
ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data/content_repairs/n01-2026-10-08-w19-polish.json"
AUDIT = Path(__file__).resolve().parent / "audit/f1p"
LOG = AUDIT / "w19_polish_log.json"
NODE_FIELDS = ("id", "level", "parent_id", "name", "name_ru", "description", "assessed_ability",
               "class_level_start", "class_level_end", "importance", "sequence_order",
               "cognitive_type", "is_active")

# M1 split (S42_01 -> S37_01 / S37_02): all 55 tasks were read; one regex misclassification found:
M1_FIX = {"G11_TB_6_8*_6_71_б": ("G11_S37_01", "G11_S37_02",
                                 "y=0,5x³+8 и y=2x+8 — площадь между двумя графиками, а не под графиком (нет y=0)")}
# residual vs structure conflicts (targets differ).  Rule: the more specific target wins; a real skill beats NULL.
CONFLICT_WIN = {
    "G10_TB_2_3_9": ("residual", "G8_S15_09 «наибольшее целое решение» точнее, чем G10_S10_04 (целые решения системы): задача — одно линейное неравенство"),
    "G10_TB_§4_4_5_1": ("structure", "G10_S07_12 «равносильные преобразования» точнее, чем простое линейное неравенство G8_S15_01: вопрос о равносильности"),
}
NULL_LOSES = "реальный навык точнее NULL"
# Independent check of w19: these moves were judged worse than the current / better targets exist.
DROP_MOVES = {"G10_TB_3_3_20": "остаётся на G10_S15_02", "G11_TB_14_3_3_1": "остаётся на G10_S15_02"}
RETARGET = {"G11_TB_15_4*_15_38_b": "G10_S32_01",   # was NULL
            "G11_TB_9_7*_9_56_1": "G10_S15_03"}    # was G10_S09_02 (structure); verifier: best fit

DESC = {  # nodes whose description is empty today (the update tool requires one) or becomes stale
    "G11_P13": "Обратимость функции, нахождение обратной функции, область определения и значений обратной функции, симметрия графиков относительно прямой y=x.",
    "G11_P14": "Арксинус, арккосинус, арктангенс, арккотангенс: определения, области определения и значений, свойства и графики.",
    "G11_P15": "Применение обратных тригонометрических функций: композиции, упрощение выражений, вычисление сумм аркфункций.",
    "G10_P05": "Чётность и нечётность, промежутки возрастания и убывания, экстремумы, наибольшее и наименьшее значения функции.",
    "G10_P06": "Сдвиг, растяжение, сжатие и отражение графика функции; определение преобразования по графику.",
    "G11_P18": "Приращение функции и дифференциал, связь дифференциала с производной.",
    "G10_P23": "Арксинус, арккосинус, арктангенс, арккотангенс: значения, свойства, композиции с тригонометрическими функциями.",
    "G11_P02": "Нахождение области определения (дробь, корень, комбинированные условия), область значений и ограниченность функции.",
    "G10_T04": "Уравнения, неравенства и системы с корнями: ОДЗ, возведение в степень, равносильные переходы.",
    "G10_T09": "Перестановки, размещения, сочетания, бином Ньютона, случайные события, определения вероятности, независимые события.",
    "G10_T06": "Логарифм и его свойства, логарифмическая функция, логарифмические уравнения, неравенства и системы с показательными функциями.",
    "G10_T08": "Простейшие и сводящиеся к ним тригонометрические уравнения, методы решения, тригонометрические неравенства.",
    "G11_S37_02": "Площадь фигуры, ограниченной графиками функций, касательными и прямыми x=a, x=b: поиск пределов интегрирования и вычисление интеграла разности.",
    "G11_S38_01": "Вычисление определённого интеграла как площади (со знаком) по рисунку: полукруг, треугольник, трапеция, интегралы от модуля.",
    "G10_S05_04": "Промежутки возрастания и убывания функции: исследование монотонности, в том числе синуса и косинуса, сравнение значений.",
    "G11_S19_02": "Применение правила (u/v)' = (u'v − uv')/v² к дроби, в том числе с тригонометрическими и логарифмическими функциями.",
    "G11_S42_04": "Путь по скорости, масса стержня по плотности, работа силы, в том числе упругой, через определённый интеграл.",
}
REPARENT = [  # (node, new parent, extra set)
    ("G11_P13", "G11_T01", {}), ("G11_P14", "G11_T01", {}), ("G11_P15", "G11_T01", {}),
    ("G11_S12_02", "G11_P13", {"sequence_order": 4}),
    ("G10_P05", "G10_T01", {}), ("G10_P06", "G10_T01", {}),
]
L3L2_RENAMES = {  # truncated names; G11_P04 and G11_P45 are deliberately excluded
    "G11_P18": "Дифференциал функции", "G10_T04": "Иррациональные уравнения и неравенства",
    "G10_T09": "Комбинаторика, вероятность и события", "G10_T06": "Логарифмические функции, уравнения и неравенства",
    "G10_T08": "Тригонометрические уравнения и неравенства", "G10_P23": "Обратные тригонометрические функции и их свойства",
    "G11_P02": "Область определения и область изменения функции",
}
MIN_L4 = 5


def read_jsonl(path):
    return [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]


def main() -> None:
    engine = create_engine(os.environ["CONTENT_REPAIR_DATABASE_URL"])
    sd = json.load(open(AUDIT / "structure_decisions.json", encoding="utf-8"))
    res = {}
    for f in sorted(glob.glob(str(AUDIT / "residual_*_out.jsonl"))):
        for r in read_jsonl(f):
            assert r["id"] not in res
            res[r["id"]] = r
    tm = sd["task_moves"]
    st = {}
    for x in tm["required"] + tm["recommended_minor_reaudit"] + [y for g in tm["from_merges"].values() for y in g]:
        assert x["task"] not in st
        st[x["task"]] = dict(x)
    for t, (was, now, why) in M1_FIX.items():
        assert st[t]["to_skill"] == was, t
        st[t].update(to_skill=now, why=why + " (проверено вручную)")
    merges = {m["id"]: m for m in sd["merges"]}
    absorbed = sorted(a for m in merges.values() for a in m["deactivate"])
    assert absorbed == sorted(sd["deactivate_after_move"]), absorbed

    with engine.connect() as conn:
        K = {r["id"]: dict(r) for r in conn.execute(text("SELECT * FROM knowledge_hierarchy")).mappings()}
        T = {r["id"]: dict(r) for r in conn.execute(text(
            "SELECT id, skill_id, toc_id FROM tasks_master WHERE is_active")).mappings()}
        for i in list(res) + list(st):
            if i not in T:
                raise SystemExit("task missing/inactive: " + i)
        for i, r in res.items():
            if r["from"] != T[i]["skill_id"]:
                raise SystemExit("residual source drift: " + i)
        for i, x in st.items():
            if x["from_skill"] != T[i]["skill_id"]:
                raise SystemExit("structure source drift: " + i)
        redirect = {m["absorb"]: m["keep"] for m in merges.values()}
        for i in DROP_MOVES:
            res.pop(i, None)
            st.pop(i, None)

        tgt, how, conflicts = {}, {}, []
        for i, r in sorted(res.items()):
            to = r["to"]
            if to == "NOFIT":
                continue                       # keeps the current skill
            to = None if to == "NULL" else redirect.get(to, to)
            tgt[i] = to
            how[i] = ("residual", "%s (confidence %s)" % (r["why"], r["confidence"]))
        for i, x in sorted(st.items()):
            to = x["to_skill"]
            to = redirect.get(to, to)
            if i in tgt and tgt[i] != to:
                if tgt[i] is None:
                    win, why = "structure", NULL_LOSES
                elif i in CONFLICT_WIN:
                    win, why = CONFLICT_WIN[i]
                else:
                    raise SystemExit("unresolved conflict: %s residual=%s structure=%s" % (i, tgt[i], to))
                conflicts.append({"task": i, "residual": tgt[i], "structure": to, "winner": win, "why": why})
                if win == "residual":
                    continue
            tgt[i] = to
            how[i] = ("structure", "%s: %s (tier %s)" % (x["group"], x["why"], x["tier"]))
        for i, to in RETARGET.items():
            assert i in tgt and i not in DROP_MOVES, i
            tgt[i] = to
            how[i] = ("residual" if i in res else "structure",
                      "уточнено независимой проверкой w19: лучший навык %s (было %s)" % (to, how[i][1]))
        # every task on an absorbed skill must have moved
        for a in absorbed:
            left = [i for i, t in T.items() if t["skill_id"] == a and i not in tgt]
            if left:
                raise SystemExit("tasks left on absorbed %s: %s" % (a, left[:3]))
        for i in list(tgt):
            if tgt[i] == T[i]["skill_id"]:
                del tgt[i]
        for i, to in tgt.items():
            if to is None:
                if T[i]["toc_id"] is None:
                    raise SystemExit("NULL without toc_id: " + i)
            elif to not in K or not K[to]["is_active"] or to in absorbed:
                raise SystemExit("bad target %s for %s" % (to, i))

        # ------------------------------------------------------------ taxonomy
        def row(i):
            return {k: K[i][k] for k in NODE_FIELDS}

        updates = {}
        for i, nr in sorted(L3L2_RENAMES.items()):
            updates[i] = {"name": nr, "name_ru": nr, "description": DESC[i]}
        for i, new_parent, extra in REPARENT:
            assert i not in updates or i in DESC
            s = updates.setdefault(i, {})
            s["parent_id"] = new_parent
            if K[i]["description"] is None:
                s["description"] = DESC[i]
            s.update(extra)
        renames = [x for x in sd["renames"]]
        assert len(renames) == 12
        for x in renames:
            i = x["id"]
            assert K[i]["name_ru"] == x["old_name_ru"], i
            s = updates.setdefault(i, {})
            s.update(name=x["new_name"], name_ru=x["new_name_ru"])
            if i in DESC:
                s["description"] = DESC[i]
        # sequence_order collisions among siblings after the reparent
        for i, s in updates.items():
            p = s.get("parent_id", K[i]["parent_id"])
            seq = s.get("sequence_order", K[i]["sequence_order"])
            clash = [j for j in K if j != i and K[j]["parent_id"] == p and K[j]["is_active"]
                     and K[j]["sequence_order"] == seq and updates.get(j, {}).get("parent_id", K[j]["parent_id"]) == p
                     and updates.get(j, {}).get("sequence_order", K[j]["sequence_order"]) == seq]
            if clash:
                raise SystemExit("sequence_order clash %s under %s: %s" % (i, p, clash))
        knowledge_update = [{"id": i, "before": row(i), "set": updates[i]} for i in sorted(updates)]
        knowledge_deactivate = [{"id": a, "before": row(a)} for a in absorbed]

        # ------------------------------------------------------------ repairs
        ids = sorted(tgt)
        rows = {r["id"]: r for r in gr._load(conn, ids, False)}
        names = {s: k["name_ru"] for s, k in K.items()}
        for i, s in updates.items():
            if "name_ru" in s:
                names[i] = s["name_ru"]

        def nm(s):
            return "«%s» (%s)" % (names.get(s, "?"), s) if s else "без навыка (NULL, есть toc_id)"

        repairs = []
        for i in ids:
            r_, old, new = rows[i], T[i]["skill_id"], tgt[i]
            src, det = how[i]
            reason = "перепривязка навыка %s → %s: %s" % (nm(old), nm(new), det)
            if src == "structure" and old in absorbed:
                reason += "; навык %s упраздняется (слияние в %s)" % (old, redirect[old])
            ev = ("Волна w19 (полировка 10–11 кл.), %s. " %
                  ("остаточная разметка residual_*_out.jsonl" if src == "residual" else "решения structure_decisions.json"))
            if new is None:
                ev += "Подходящего активного навыка нет; у задачи есть toc_id. "
            e = {"id": i, "before_sha256": gr.fingerprint(r_), "reason": reason,
                 "evidence": ev + "Целевой навык активен после волны. Меняется только skill_id; условие, ключ и дистракторы не тронуты.",
                 "changes": {"skill_id": new}}
            gr.validate_entry(e)
            e["after_sha256"] = gr.fingerprint(gr.candidate(r_, e, BATCH))
            repairs.append(e)

        # ------------------------------------------------------------ simulated final-state checks
        fin = {i: (tgt[i] if i in tgt else t["skill_id"]) for i, t in T.items()}
        inactive_after = {s for s, k in K.items() if not k["is_active"]} | set(absorbed)
        bad_inactive = sorted(i for i, s in fin.items() if s is not None and s in inactive_after)
        null_no_toc = sorted(i for i, s in fin.items() if s is None and T[i]["toc_id"] is None)
        parent_after = {s: updates.get(s, {}).get("parent_id", k["parent_id"]) for s, k in K.items()}
        cnt = collections.Counter(fin.values())

        def tree_counts(par):
            c = collections.Counter()
            for s, n in cnt.items():
                while s:
                    c[s] += n
                    s = par.get(s)
            return c
        empty_after = sorted(s for s, k in K.items() if s not in inactive_after and k["is_active"]
                             and k["level"] in ("L2", "L3") and tree_counts(parent_after)[s] == 0)
        par_before = {s: k["parent_id"] for s, k in K.items()}
        cnt_b = collections.Counter(t["skill_id"] for t in T.values())
        c_b = collections.Counter()
        for s, n in cnt_b.items():
            while s:
                c_b[s] += n
                s = par_before.get(s)
        empty_before = sorted(s for s, k in K.items() if k["is_active"] and k["level"] in ("L2", "L3") and c_b[s] == 0)
        thin = sorted((s, cnt.get(s, 0)) for s, k in K.items() if k["is_active"] and k["level"] == "L4"
                      and s not in inactive_after and s[:3] in ("G10", "G11") and cnt.get(s, 0) < MIN_L4)
        tasks_on_deact = sorted(i for i, s in fin.items() if s in set(absorbed))

    manifest = {"batch": BATCH, "mode": "in_place_owner_requested",
                "source_checked_at": "2026-10-08T00:00:00Z", "student_data_included": False,
                "knowledge_update": knowledge_update, "knowledge_deactivate": knowledge_deactivate,
                "repairs": repairs}
    OUT.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    LOG.write_text(json.dumps({"conflicts": conflicts, "M1_fix": list(M1_FIX),
                               "empty_L2L3_after": empty_after, "empty_L2L3_before": empty_before,
                               "thin_L4_lt5": thin}, ensure_ascii=False, indent=1) + "\n")
    srcs = collections.Counter(how[i][0] for i in ids)
    print(OUT)
    print("repairs", len(repairs), dict(srcs), "-> NULL", sum(1 for i in ids if tgt[i] is None),
          "| conflicts", len(conflicts), [(c["task"][-18:], c["winner"]) for c in conflicts])
    print("update", len(knowledge_update), "(reparents %d, L4 renames %d, L2/L3 renames %d)" % (
        len(REPARENT), len(renames), len(L3L2_RENAMES)), "| deactivate", len(knowledge_deactivate), "| merges", len(merges))
    print("CHECK active tasks on inactive skills:", len(bad_inactive), "| tasks left on deactivated:", len(tasks_on_deact),
          "| NULL skill & NULL toc:", len(null_no_toc))
    print("CHECK active L2/L3 without tasks: after", empty_after, "(before:", empty_before, ")")
    print("L4 (G10/G11) with <%d tasks: %d, to author %d" % (MIN_L4, len(thin), sum(MIN_L4 - n for _, n in thin)))
    if bad_inactive or tasks_on_deact or null_no_toc:
        sys.exit(2)


if __name__ == "__main__":
    main()
