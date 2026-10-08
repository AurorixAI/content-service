"""Build manifest n01-2026-10-07-w15-G11 (grade-11 skill remapping wave). Reads the local DB only (SELECT).

Inputs (tools/content_review/audit/f1):
  map_G11_part_01..30.jsonl  + overrides_G11.jsonl      final mapping of 3 522 tasks
  verify_G11_map.jsonl                                  independent check; its 5 "disagree" cases are applied
  complex_design.json                                   complex-number subtree (nodes, activation, edges, tasks)
  new_skills_G11.json, new_skills_G11_extra.json        new L4 nodes and 2 reactivations

Refinements applied on top (see REFINEMENTS below), then the manifest is written:
  knowledge_nodes (new, active), knowledge_activate (complex section + reactivations),
  prerequisites (complex design only: existing edges are keyed L3->L3, new L4 need none),
  repairs (skill_id only).

Usage (from content-service):
  CONTENT_REPAIR_DATABASE_URL=... python3 -m tools.content_review.build_w15_G11
Deterministic: the same DB state and inputs give a byte-identical manifest.
"""
from __future__ import annotations

import collections
import glob
import json
import os
import re
import statistics
import sys
from pathlib import Path

from sqlalchemy import create_engine, text

from tools.content_review import guarded_repair as gr

BATCH = "n01-source-repair-2026-10-07-w15-G11"
ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data/content_repairs/n01-2026-10-07-w15-G11.json"
AUDIT = Path(__file__).resolve().parent / "audit/f1"
LOG = AUDIT / "w15_G11_consistency.json"

NODE_FIELDS = ("id", "level", "parent_id", "name", "name_ru", "description", "assessed_ability",
               "class_level_start", "class_level_end", "importance", "sequence_order",
               "cognitive_type", "is_active")
# Applied after the independent check (verify_G11_map.jsonl, verdict "disagree").
VERIFY_CORRECTIONS = {
    "G11_TB_10_2_6_1": "G10_S07_03", "G11_TB_10_2_6_2": "G10_S07_03",
    "G11_TB_11_6*_11_43*_a": "G10_S11_07", "G11_TB_11_6*_11_43*_б": "G10_S11_07",
    "G11_TB_§19_15_1": "G11_S05_04",
}

# ---- refinement 2: remarkable limits -------------------------------------------------------
LIMIT_NODE = {
    "id": "G11_S11_04", "level": "L4", "parent_id": "G11_P11",
    "name": "Замечательные пределы", "name_ru": "Замечательные пределы",
    "description": "Первый замечательный предел sin x/x → 1 и его следствия (tg x/x, arcsin x/x, (1−cos x)/x²), "
                   "второй замечательный предел (1+1/x)^x → e и (1+x)^(1/x) → e; приведение предела к стандартному виду.",
    "assessed_ability": "Свести предел к замечательному (замена аргумента, домножение на постоянную) и вычислить его.",
    "class_level_start": 11, "class_level_end": 11, "sequence_order": 4, "cognitive_type": "apply",
    "is_active": True}
LIMIT_FALLBACK = "G11_S11_02"
LIM = re.compile(r"\\lim")
LIM_TRIG = re.compile(r"sin|tan|tg|arcsin|arctg|arctan|\\cos|cos")
LIM_BAD_POINT = re.compile(r"\\to\s*(-?\\?pi|\\frac\{\\pi|\\infty|\+\\infty|-\\infty)|\\to\s*\\frac\{\\pi")
LIM_E = re.compile(r"\(1\s*[+\-]|\\frac\{2\+x\}\{2\}")
LIM_POW = re.compile(r"\)\s*\^")
# ---- derivative of rational fraction -------------------------------------------------------
TRIG = re.compile(r"sin|cos|tg|tan|ctg|cot|arc")
TRANS = re.compile(r"ln|\\log|\\exp|e\^|\be\b")
FRACTIONISH = re.compile(r"\\frac|\\dfrac|\\sqrt|/")
# ---- refinement 3: inactive stubs holding tasks -------------------------------------------
# Owner rule: no active task may end with skill_id NULL, so every stub task goes to the nearest active skill.
STUB_DEST = {
    "G10_S27_04": "G10_S27_05",  # A∪B, A∩B для кубика -> алгебра событий (new)
    "G10_S30_01": "G8_S28_05",   # репрезентативность выборки: как и остальные задачи гл. 23 §1 (map)
    "G10_S16_05": "G10_S18_01",  # когда log f = log g равносильно f = g -> простейшее логарифмическое уравнение
    "G10_S09_06": "G10_S09_02",  # знак частного f/g > 0 -> метод интервалов для дробно-рациональных
    "G11_S19_03": "G11_S19_02",  # формула (u/v)' (после перенос рациональных дробей на S17 здесь остаются дроби с трансцендентными функциями)
    "G11_S20_02": "G11_S17_02",  # (x^n)' = n x^{n-1}, n действительное -> производная степенной функции (new)
    "G9_S39_01": "G9_S28_03",    # шаг индукции S_{n+1}=S_n+a_{n+1}: рекуррентная последовательность (как и две соседние задачи про числа Фибоначчи); <5 задач на индукцию, отдельный L4 не создаётся
    "G9_S40_01": "G9_S16_04",    # противоречие 5·10^k−1 ≥ 10^k: доказательство методом оценки
}
REACTIVATE = {  # reactivations from new_skills_G11*.json; extra fields refreshed for the new meaning
    "G10_S16_04": {
        "name": "Сравнение логарифмов (монотонность логарифмической функции)",
        "description": "Сравнение логарифмов с одинаковым основанием и разными основаниями по возрастанию или убыванию "
                       "логарифмической функции; выбор знака неравенства по основанию a>1 или 0<a<1.",
        "assessed_ability": "Сравнить значения логарифмов, определив характер монотонности по основанию."},
    "G11_S09_04": {
        "name": "Предел по определению (ε–δ, ε–N)",
        "description": "Определение предела функции и последовательности: подбор δ(ε) и N(ε), доказательство предела по определению.",
        "assessed_ability": "Найти допустимый радиус окрестности δ или номер N для заданной точности ε и обосновать предел по определению."},
}
# ---- refinement 4: closest skill for new nodes that end with <5 tasks ----------------------
# ---- owner review: taxonomy parents -------------------------------------------------------
# New L3 nodes (all active, class 10).  L4 children are re-numbered to the new P number.
NEW_L3 = [
    {"id": "G10_P31", "parent_id": "G10_T09", "name": "Комбинаторика", "importance": 9, "sequence_order": 31,
     "cognitive_type": "apply",
     "description": "Соединения без повторений: перестановки, размещения, сочетания, уравнения с A_n^k и C_n^k, бином Ньютона."},
    {"id": "G10_P32", "parent_id": "G10_T03", "name": "Уравнения и неравенства с параметром", "importance": 9,
     "sequence_order": 32, "cognitive_type": "analyze",
     "description": "Исследование рациональных уравнений, неравенств и их систем, содержащих параметр: число решений, условия на параметр."},
    {"id": "G10_P33", "parent_id": "G10_T04", "name": "Иррациональные неравенства", "importance": 8,
     "sequence_order": 33, "cognitive_type": "apply",
     "description": "Неравенства с корнями: равносильные переходы к системам и совокупностям, учёт ОДЗ и знака обеих частей."},
    {"id": "G10_P34", "parent_id": "G10_T03", "name": "Уравнения и неравенства с модулем", "importance": 9,
     "sequence_order": 34, "cognitive_type": "apply",
     "description": "Аналитические методы решения уравнений и неравенств с модулем: раскрытие по знакам, замена, совокупности и системы."},
]
# New L4 whose parent L3 did not fit its topic: old id -> new id (parent changes with it).
RENAME = {
    "G10_S28_07": "G10_S31_01", "G10_S28_08": "G10_S31_02", "G10_S28_06": "G10_S31_03",   # -> G10_P31 Комбинаторика
    "G10_S09_07": "G10_S32_01", "G10_S08_11": "G10_S32_02",                               # -> G10_P32 параметр
    "G10_S11_07": "G10_S33_01",                                                           # -> G10_P33 иррац. неравенства
    "G11_S07_04": "G10_S34_01",                                                           # -> G10_P34 модуль
    "G10_S28_09": "G10_S29_01",                                                           # existing stub G10_S29_01 is reactivated instead
}
L4_PARENT = {"G10_S31_01": "G10_P31", "G10_S31_02": "G10_P31", "G10_S31_03": "G10_P31",
             "G10_S32_01": "G10_P32", "G10_S32_02": "G10_P32", "G10_S33_01": "G10_P33", "G10_S34_01": "G10_P34"}
L4_SEQ = {"G10_S31_01": 1, "G10_S31_02": 2, "G10_S31_03": 3, "G10_S32_01": 1, "G10_S32_02": 2,
          "G10_S33_01": 1, "G10_S34_01": 1}
# Reactivated independent-events branch (L3 G10_P29 + L4 G10_S29_01) replaces the new node G10_S28_09.
REACTIVATE_L3 = {
    "G10_P29": {"name": None, "importance": 8,
                "description": "Независимые события, вероятность совместного наступления независимых событий и их дополнений."},
}
REACTIVATE["G10_S29_01"] = {
    "name": "Независимые события и умножение вероятностей",
    "description": "Независимость событий; P(AB)=P(A)P(B) для независимых событий, вероятность хотя бы одного события, "
                   "серии независимых испытаний.",
    "assessed_ability": "Распознать независимые события и найти вероятность их совместного наступления по правилу умножения."}
def _edge(s, p, t, w, c, d):
    return {"skill_id": s, "prerequisite_id": p, "dependency_type": t, "weight": w, "criticality": c,
            "relationship_description": d, "discovery_source": "expert"}
EXTRA_EDGES = [
    _edge("G10_P31", "G7_P36", "hard", 0.8, 8, "Формулы перестановок, размещений и сочетаний опираются на правило произведения и суммы."),
    _edge("G10_P31", "G7_P37", "hard", 1.0, 9, "Перестановки, размещения и сочетания впервые различаются в 7 классе; в 10 классе добавляются формулы и уравнения."),
    _edge("G10_P31", "G8_P31", "soft", 0.7, 7, "Основной закон комбинаторики 8 класса — основа вычисления числа соединений по формулам."),
    _edge("G10_P28", "G10_P31", "hard", 0.8, 8, "Классическая вероятность требует подсчёта числа исходов и благоприятных исходов через соединения."),
    _edge("G10_P29", "G10_P27", "hard", 1.0, 9, "Независимость определяется для событий и их операций."),
    _edge("G10_P29", "G10_P28", "hard", 0.9, 9, "Правило умножения вероятностей формулируется через определение вероятности."),
    _edge("G10_P32", "G10_P07", "hard", 1.0, 9, "Уравнение с параметром решается как рациональное уравнение при каждом допустимом значении параметра."),
    _edge("G10_P32", "G10_P09", "hard", 0.9, 9, "Неравенства с параметром требуют метода интервалов для рациональных выражений."),
    _edge("G10_P32", "G10_P08", "soft", 0.7, 7, "Системы с параметром используют методы решения систем рациональных уравнений."),
    _edge("G10_P33", "G10_P11", "hard", 1.0, 10, "Иррациональные неравенства решаются по тем же правилам ОДЗ и возведения в степень, что и уравнения."),
    _edge("G10_P33", "G10_P09", "hard", 0.8, 8, "После перехода к системе остаются рациональные неравенства, решаемые методом интервалов."),
    _edge("G10_P34", "G8_P17", "hard", 0.9, 9, "Определение модуля и простейшие уравнения и неравенства с модулем изучаются в 8 классе."),
    _edge("G10_P34", "G10_P07", "hard", 0.8, 8, "Раскрытие модуля сводит задачу к рациональным уравнениям на промежутках."),
]
MERGE_TO = {}  # node id -> closest active skill; filled below by CLOSEST_FALLBACK when needed
MIN_NEW = 5


def read_jsonl(path):
    return [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]


def norm(s):
    s = (s or "").lower().replace("{,}", ",").replace("\\left", "").replace("\\right", "")
    s = s.replace("\\,", "").replace("\\!", "").replace("\\dfrac", "\\frac").replace("\\tfrac", "\\frac")
    s = re.sub(r"[\s$]+", "", s)
    s = s.replace("\\text", "").replace("\\mathrm", "")
    return re.sub(r"[^0-9a-zа-яё\\^_{}=+\-*/()<>|]", "", s)


def median_int(vals):
    return int(round(statistics.median(vals)))


def main() -> None:
    engine = create_engine(os.environ["CONTENT_REPAIR_DATABASE_URL"])
    # ------------------------------------------------------------------ inputs
    mapping, part_of = {}, {}
    for f in sorted(glob.glob(str(AUDIT / "map_G11_part_*.jsonl"))):
        for r in read_jsonl(f):
            mapping[r["id"]] = r
            part_of[r["id"]] = Path(f).stem.replace("map_G11_", "")
    for r in read_jsonl(AUDIT / "overrides_G11.jsonl"):
        if r["id"] not in mapping:
            raise SystemExit("override for unknown task " + r["id"])
        mapping[r["id"]].update(r)
        part_of[r["id"]] += "+overrides"
    verdict = {r["id"]: r for r in read_jsonl(AUDIT / "verify_G11_map.jsonl")}
    for tid, to in VERIFY_CORRECTIONS.items():
        v = verdict[tid]
        assert v["verdict"] == "disagree" and v["my_target"] == to, tid
        mapping[tid]["to"] = to
    for r in mapping.values():
        r["to"] = RENAME.get(r["to"], r["to"])
    assert sum(1 for v in verdict.values() if v["verdict"] == "disagree") == len(VERIFY_CORRECTIONS)
    design = json.load(open(AUDIT / "complex_design.json", encoding="utf-8"))
    news = json.load(open(AUDIT / "new_skills_G11.json", encoding="utf-8")) + \
        json.load(open(AUDIT / "new_skills_G11_extra.json", encoding="utf-8"))
    complex_to = design["task_assignment"]
    new_def = {x["target"]: x for x in news if x["decision"] == "new"}
    react_ids = [x["target"] for x in news if x["decision"] == "reactivate"]
    assert set(react_ids) == set(REACTIVATE) - {"G10_S29_01"}
    complex_to = {k: RENAME.get(v, v) for k, v in complex_to.items()}

    with engine.connect() as conn:
        K = {r["id"]: dict(r) for r in conn.execute(text("SELECT * FROM knowledge_hierarchy")).mappings()}
        T = {r["id"]: dict(r) for r in conn.execute(text(
            "SELECT id, skill_id, question_text, question_latex, question_image_url "
            "FROM tasks_master WHERE is_active")).mappings()}
        edges_db = {(r[0], r[1]) for r in conn.execute(text(
            "SELECT skill_id, prerequisite_id FROM skill_prerequisites"))}
        wave = set(mapping) | set(complex_to)
        missing = [i for i in wave if i not in T]
        if missing:
            raise SystemExit("wave tasks missing/inactive: %s" % missing[:5])
        stub_tasks = {i for i, t in T.items() if t["skill_id"] in K and not K[t["skill_id"]]["is_active"]
                      and t["skill_id"] in STUB_DEST}
        scope = {i for i in T if i.startswith("G11") or (T[i]["skill_id"] or "").startswith("G11")} | wave | stub_tasks
        cur = {i: T[i]["skill_id"] for i in scope}
        for i, s in cur.items():
            if s in K and not K[s]["is_active"] and s not in STUB_DEST and not s.startswith("G11_S45") \
                    and s not in REACTIVATE:
                raise SystemExit("active task on unexpected inactive skill: %s %s" % (i, s))

        tgt = dict(cur)
        why = {i: ("keep", "") for i in scope}      # (category, detail)
        conf = {i: 0.0 for i in scope}
        # ---------------------------------------------------------- stage A: the wave
        for i, r in mapping.items():
            tgt[i] = r["to"]
            conf[i] = float(r.get("confidence") or 0)
            tag = "verify-disagree-corrected" if i in VERIFY_CORRECTIONS else \
                ("verify-" + verdict[i]["verdict"] if i in verdict else "unverified")
            why[i] = ("map", "%s; %s; %s" % (part_of[i], r.get("why") or "", tag))
        for i, s in complex_to.items():
            tgt[i] = s
            conf[i] = 1.0
            why[i] = ("complex", "")
        stage_moves = collections.Counter()

        # ---------------------------------------------------------- stage B: remarkable limits
        limit_ids = []
        for i in sorted(scope):
            if why[i][0] == "complex":
                continue
            q = T[i]["question_text"] or ""
            if not LIM.search(q):
                continue
            fr = "\\frac" in q or "\\dfrac" in q
            ratio = fr and LIM_TRIG.search(q) and not LIM_BAD_POINT.search(q) and \
                re.search(r"\\lim_\{x\s*\\to\s*(0|-?\d+)", q)
            pw = LIM_E.search(q) and LIM_POW.search(q)
            if ratio or pw:
                limit_ids.append(i)
        use_limit = len(limit_ids) >= 5
        if any(v is None for v in STUB_DEST.values()):
            raise SystemExit("stub task would get NULL skill")
        for i in limit_ids:
            tgt[i] = LIMIT_NODE["id"] if use_limit else LIMIT_FALLBACK
            why[i] = ("limit", why[i][1])
            conf[i] = max(conf[i], 0.9)
        # ---------------------------------------------------------- stage C: rational-fraction derivatives
        rational = []
        for i in sorted(scope):
            if tgt[i] != "G11_S19_02":
                continue
            q = T[i]["question_text"] or ""
            if TRIG.search(q) or TRANS.search(q):
                continue
            tgt[i] = "G11_S17_01" if FRACTIONISH.search(q) else "G11_S17_02"
            why[i] = ("rational", why[i][1])
            conf[i] = max(conf[i], 0.85)
            rational.append(i)
        # ---------------------------------------------------------- stage D: inactive stubs
        pre = collections.Counter(tgt.values())
        for stub, dest in sorted(STUB_DEST.items()):
            if pre.get(stub, 0) >= 3:
                raise SystemExit("stub %s keeps %d tasks: decide reactivation" % (stub, pre[stub]))
        stub_moved = []
        for i in sorted(scope):
            if tgt[i] in STUB_DEST:
                stub = tgt[i]
                tgt[i] = STUB_DEST[stub]
                why[i] = ("stub", stub)
                conf[i] = max(conf[i], 0.8)
                stub_moved.append(i)

        # ---------------------------------------------------------- new nodes definitions
        nodes_def = {}
        for sid, x in new_def.items():
            if sid == "G10_S28_09":
                continue  # replaced by reactivation of G10_P29 / G10_S29_01
            n = {k: x["node"][k] for k in NODE_FIELDS}
            if sid in RENAME:
                n.update(id=RENAME[sid], parent_id=L4_PARENT[RENAME[sid]], sequence_order=L4_SEQ[RENAME[sid]],
                         class_level_start=10, class_level_end=10)
                sid = RENAME[sid]
            nodes_def[sid] = n
        l3_defs = []
        for d3 in NEW_L3:
            assert d3["id"] not in K and K[d3["parent_id"]]["is_active"] and K[d3["parent_id"]]["level"] == "L2", d3["id"]
            assert not [j for j in K if K[j]["parent_id"] == d3["parent_id"] and K[j]["sequence_order"] == d3["sequence_order"]]
            l3_defs.append({"id": d3["id"], "level": "L3", "parent_id": d3["parent_id"], "name": d3["name"],
                            "name_ru": d3["name"], "description": d3["description"], "assessed_ability": None,
                            "class_level_start": 10, "class_level_end": 10, "importance": d3["importance"],
                            "sequence_order": d3["sequence_order"], "cognitive_type": d3["cognitive_type"],
                            "is_active": True})
        if use_limit:
            sib = [K[j]["importance"] for j in K if K[j]["parent_id"] == LIMIT_NODE["parent_id"] and K[j]["is_active"]]
            nodes_def[LIMIT_NODE["id"]] = dict(LIMIT_NODE, importance=median_int(sib))
            assert LIMIT_NODE["id"] not in K
            assert not [j for j in K if K[j]["parent_id"] == LIMIT_NODE["parent_id"]
                        and K[j]["sequence_order"] == LIMIT_NODE["sequence_order"]]
        for sid in nodes_def:
            if sid in K:
                raise SystemExit("new node already exists: " + sid)
        kept_new = set(nodes_def)
        dropped = {}

        def is_valid(s):
            if s is None:
                return False
            if s in kept_new or s in REACTIVATE:
                return True
            if s.startswith("G11_S45") or s.startswith("G11_S46") or s.startswith("G11_S47") or s.startswith("G11_S48"):
                return True
            return s in K and K[s]["is_active"]

        # ---------------------------------------------------------- refinements 1 & 4 (iterated)
        groups_log = []
        parent = {}

        def find(a):
            while parent.setdefault(a, a) != a:
                parent[a] = parent[parent[a]]
                a = parent[a]
            return a

        keymap = collections.defaultdict(list)
        for i in sorted(scope):
            img = T[i]["question_image_url"] or ""
            for fld in ("question_text", "question_latex"):
                n = norm(T[i][fld] if T[i][fld] else T[i]["question_text"])
                if len(n) >= 12:
                    keymap[(n, img)].append(i)
        for ids in keymap.values():
            for j in ids[1:]:
                parent[find(j)] = find(ids[0])
        comps = collections.defaultdict(list)
        for i in sorted(scope):
            if i in parent:
                comps[find(i)].append(i)
        groups = [sorted(v) for v in comps.values() if len(v) > 1]
        groups.sort()
        catch_all = {"G11_S01_01", "G11_S01_02", "G11_S01_03", "G11_S02_01"}
        changed_consistency = {}

        def consistency():
            changed = 0
            for g in groups:
                votes = collections.Counter(tgt[i] for i in g if is_valid(tgt[i]))
                if len(set(tgt[i] for i in g)) == 1 or not votes:
                    continue
                top = max(votes.values())
                cands = [s for s, v in votes.items() if v == top]
                if len(cands) > 1:
                    def score(s):
                        wconf = max([conf[i] for i in g if tgt[i] == s and why[i][0] != "keep"] or [0.0])
                        return (s not in catch_all, wconf, -sum(1 for t in tgt.values() if t == s), s)
                    cands.sort(key=score, reverse=True)
                win = cands[0]
                for i in g:
                    if tgt[i] != win:
                        changed_consistency.setdefault(i, []).append((tgt[i], win))
                        tgt[i] = win
                        if why[i][0] in ("keep", "map", "complex"):
                            why[i] = ("consistency", why[i][1])
                        changed += 1
            return changed

        for _round in range(10):
            cnt = collections.Counter(tgt.values())
            small = [s for s in sorted(kept_new) if cnt.get(s, 0) < MIN_NEW]
            for s in small:
                dest = MERGE_TO.get(s)
                if not dest or not is_valid(dest):
                    raise SystemExit("new node %s has %d tasks (<%d); define MERGE_TO" % (s, cnt.get(s, 0), MIN_NEW))
                kept_new.discard(s)
                dropped[s] = (dest, cnt.get(s, 0))
                for i in scope:
                    if tgt[i] == s:
                        tgt[i] = dest
                        why[i] = ("merge", s)
                        conf[i] = max(conf[i], 0.7)
            ch = consistency()
            if not small and not ch:
                break
        else:
            raise SystemExit("consistency/merge did not converge")
        for s in dropped:
            nodes_def.pop(s, None)
        final_cnt = collections.Counter(tgt.values())
        if sum(1 for s in kept_new if final_cnt.get(s, 0) < MIN_NEW):
            raise SystemExit("new node below minimum")

        # ---------------------------------------------------------- taxonomy payload
        for s in kept_new:
            n = nodes_def[s]
            assert n["parent_id"] in K and K[n["parent_id"]]["is_active"] or n["parent_id"] in {d3["id"] for d3 in NEW_L3}
        knowledge_nodes = [dict(n) for n in design["nodes"]] + l3_defs + [nodes_def[s] for s in sorted(kept_new)]
        for n in knowledge_nodes:
            assert list(n) and set(n) == set(NODE_FIELDS), n["id"]
            assert n["id"] not in K, n["id"]
        activations = []
        for before in design["activate_before"]:
            i = before["id"]
            cur_row = {k: K[i][k] for k in NODE_FIELDS}
            if cur_row != before:
                raise SystemExit("complex activation before-row drift: " + i)
            activations.append({"id": i, "before": before, "set": design["activate_set"][i]})
        for i, r3 in sorted(REACTIVATE_L3.items()):
            before = {k: K[i][k] for k in NODE_FIELDS}
            assert before["is_active"] is False and before["level"] == "L3"
            activations.append({"id": i, "before": before,
                                "set": {"importance": r3["importance"], "description": r3["description"]}})
        for i in sorted(REACTIVATE):
            before = {k: K[i][k] for k in NODE_FIELDS}
            assert before["is_active"] is False
            r = REACTIVATE[i]
            activations.append({"id": i, "before": before,
                                "set": {"importance": 8, "name": r["name"], "name_ru": r["name"],
                                        "description": r["description"], "assessed_ability": r["assessed_ability"]}})
        prerequisites = [dict(e) for e in design["prerequisites"]] + [dict(e) for e in EXTRA_EDGES]
        # existing edges are L3 -> L3 only; new L4 need no per-L4 edges, nothing is duplicated
        seen_edges = set()
        for e in prerequisites:
            key = (e["skill_id"], e["prerequisite_id"])
            assert key not in edges_db and key not in seen_edges and (key[1], key[0]) not in seen_edges, e
            seen_edges.add(key)

        # ---------------------------------------------------------- repairs
        ids = sorted(i for i in scope if tgt[i] != cur[i])
        rows = {r["id"]: r for r in gr._load(conn, ids, False)}
        names = {s: K[s]["name_ru"] for s in K}
        names.update({s: n["name_ru"] for s, n in nodes_def.items()})
        names.update({s: REACTIVATE[s]["name"] for s in REACTIVATE})
        names.update({n["id"]: n["name_ru"] for n in design["nodes"]})
        names.update({n["id"]: n["name_ru"] for n in l3_defs})

        def nm(s):
            return "«%s» (%s)" % (names.get(s, "?"), s) if s else "без навыка (NULL)"

        repairs = []
        for i in ids:
            row, old, new = rows[i], cur[i], tgt[i]
            cat, det = why[i]
            head = "перепривязка навыка %s → %s" % (nm(old), nm(new))
            if cat == "map":
                reason = "%s: %s" % (head, det.split("; ")[1] or "по содержанию задачи")
                ev = ("Волна w15, независимая разметка %s (confidence %.2f); проверка verify_G11_map: %s. "
                      % (det.split("; ")[0], conf[i], det.split("; ")[2]))
            elif cat == "complex":
                reason = head + ": задача по комплексным числам; поддерево G11_COMPLEX активируется этой волной"
                ev = "complex_design.json (task_assignment): раздел комплексных чисел (алгебраическая форма, сопряжение, модуль, формы записи, корни). "
            elif cat == "limit":
                reason = head + ": предел типа замечательного (sin x/x, (1+1/x)^x и т.п.)" + \
                    ("" if use_limit else "")
                ev = "Условие содержит предел с тригонометрической функцией при x→a или степенно-показательной формой (1+u)^v; нужен приём замечательных пределов, а не разложение на множители. "
            elif cat == "rational":
                reason = head + ": производная рациональной дроби/корня без тригонометрии"
                ev = "Условие — дифференцирование алгебраической дроби/корня, тригонометрических и трансцендентных функций нет; навык G11_S19_02 относится к дробям с тригонометрией. "
            elif cat == "stub":
                reason = head + ": прежний навык %s неактивен (заглушка с <3 задач), задача перенесена на тематически ближайший" % det
                ev = "Навык-заглушка %s неактивен и после волны содержал бы <3 задач; целевая тема совпадает с содержанием задачи. " % det
            elif cat == "merge":
                reason = head + ": новый навык %s набрал <%d задач и объединён с ближайшим" % (det, MIN_NEW)
                ev = "Правило волны w15: новый навык с <%d задач не создаётся. " % MIN_NEW
            elif cat == "consistency":
                reason = head + ": задачи с одинаковым условием должны относиться к одному навыку"
                ev = "Совпадающее (нормализованное) условие у нескольких задач; выбран навык большинства/наиболее специфичный. "
            else:
                reason = head
                ev = ""
            e = {"id": i, "before_sha256": gr.fingerprint(row), "reason": reason,
                 "evidence": ev + "Целевой навык активен после волны. Меняется только skill_id; условие, ключ и дистракторы не тронуты.",
                 "changes": {"skill_id": new}}
            gr.validate_entry(e)
            e["after_sha256"] = gr.fingerprint(gr.candidate(row, e, BATCH))
            repairs.append(e)

        # ---------------------------------------------------------- checks
        active_after = {s for s, k in K.items() if k["is_active"]} | set(kept_new) | set(REACTIVATE) | \
            {a["id"] for a in design["activate_before"]} | {n["id"] for n in design["nodes"]} | \
            {n["id"] for n in l3_defs} | set(REACTIVATE_L3)
        bad_inactive = sorted(i for i in scope if tgt[i] is not None and tgt[i] not in active_after)
        g11_null = sorted(i for i in scope if tgt[i] is None and (i.startswith("G11") or cur[i] is None or (cur[i] or "").startswith("G11")))
        # bank-wide: every active task not in scope keeps its skill; those on inactive skills must be zero
        outside_bad = sorted(i for i, t in T.items() if i not in scope and t["skill_id"] and t["skill_id"] not in active_after)
        g11_l4 = sorted(s for s in active_after if (K.get(s) or next((n for n in knowledge_nodes if n["id"] == s), {})).get("level") == "L4"
                        and s.startswith("G11"))
        all_cnt = collections.Counter(tgt[i] for i in scope)
        for i, t in T.items():
            if i not in scope:
                all_cnt[t["skill_id"]] += 0  # outside tasks counted below
        full_cnt = collections.Counter()
        for i, t in T.items():
            full_cnt[tgt[i] if i in scope else t["skill_id"]] += 1
        empty = [s for s in g11_l4 if full_cnt.get(s, 0) == 0]
        lvl = {s: K[s] for s in K}
        lvl.update({n["id"]: n for n in knowledge_nodes})
        lvl["G10_S29_01"] = dict(K["G10_S29_01"], parent_id="G10_P29")
        L2 = collections.Counter()
        L3 = collections.Counter()
        for s, n_ in full_cnt.items():
            if not s or s not in lvl or not s.startswith("G11"):
                continue
            p3 = lvl[s]["parent_id"] if lvl[s]["level"] == "L4" else s
            p2 = lvl[p3]["parent_id"]
            L3[p3] += n_
            L2[p2] += n_

    manifest = {"batch": BATCH, "mode": "in_place_owner_requested",
                "source_checked_at": "2026-10-07T00:00:00Z", "student_data_included": False,
                "knowledge_allow_active": True,
                "knowledge_nodes": knowledge_nodes, "knowledge_activate": activations,
                "prerequisites": prerequisites, "repairs": repairs}
    OUT.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    LOG.write_text(json.dumps({
        "consistency_groups": len(groups),
        "consistency_changes": {i: v for i, v in sorted(changed_consistency.items())},
        "limits": limit_ids, "rational": rational, "stub_moved": stub_moved,
        "dropped_new_nodes": dropped,
        "empty_g11_l4": empty,
        "L2": dict(sorted(L2.items())), "L3": dict(sorted(L3.items())),
    }, ensure_ascii=False, indent=1) + "\n")

    cat_cnt = collections.Counter(why[i][0] for i in ids)
    print(OUT)
    print("repairs", len(repairs), "by category", dict(cat_cnt), "skill_id->NULL", sum(1 for e in repairs if e["changes"]["skill_id"] is None))
    print("nodes new", len(knowledge_nodes), "(complex %d, other %d)" % (len(design["nodes"]), len(knowledge_nodes) - len(design["nodes"])),
          "activate", len(activations), "edges", len(prerequisites), "dropped(<5)", dropped)
    print("limits", len(limit_ids), "->", LIMIT_NODE["id"] if use_limit else LIMIT_FALLBACK, "| rational S19_02->S17", len(rational),
          "| stub moved", len(stub_moved), "| consistency groups", len(groups), "changed tasks", len(changed_consistency))
    touched_null = [e["id"] for e in repairs if e["changes"]["skill_id"] is None]
    print("CHECK active G11 tasks with NULL skill after wave:", len(g11_null), g11_null[:5],
          "| wave-touched tasks left NULL:", len(touched_null), "| NULL introduced by wave:", len(touched_null))
    if touched_null:
        sys.exit(2)
    print("CHECK wave tasks on inactive skills:", len(bad_inactive), bad_inactive[:5],
          "| outside-wave active tasks on inactive skills:", len(outside_bad), outside_bad[:5])
    print("CHECK empty active G11 L4 (%d):" % len(empty), ", ".join(empty))
    print("L2:", dict(sorted(L2.items())))
    print("L3:", " ".join("%s=%d" % (k[4:], v) for k, v in sorted(L3.items())))
    if bad_inactive or g11_null or outside_bad:
        sys.exit(2)


if __name__ == "__main__":
    main()
