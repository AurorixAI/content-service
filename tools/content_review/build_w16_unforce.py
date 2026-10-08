"""Build manifest n01-2026-10-08-w16 (return forced skill mappings to NULL, skill_id only). Reads the local DB only.

Owner rule (2026-10-08): a task gets a skill only when the skill clearly fits; if unsure skill_id stays NULL
(the task is still used in exams through toc_id).  Wave 15 forced uncertain tasks onto the "nearest" skill.

Candidate pool (audit/f1):
  overrides_G11.jsonl   why mentions nearest / ближайш / no exact skill / олимпиад / forced, or confidence < 0.7
  verify_G11_map.jsonl  verdict "acceptable" whose reason says the exact skill does not exist
  G9_TB_31_629, G9_TB_ЗПТ_888
  new_skills_G11.json   decision "existing" (clusters < 5 tasks mapped to an existing skill)
  w15 manifest          stub-moved tasks ("заглушка с <3 задач")
  map_G11_part_*.jsonl  tasks the mapper first sent to NONE (olympiad/rare topics)
Each candidate was read by hand against its CURRENT skill (local DB after w15).  NULL_REASON holds the
tasks whose skill is a stretch; every other candidate keeps its skill.  Safety nets: a task returns to NULL
only if toc_id IS NOT NULL, and no active skill may be left without active tasks.

Usage (from content-service):
  CONTENT_REPAIR_DATABASE_URL=... python3 -m tools.content_review.build_w16_unforce
Writes data/content_repairs/n01-2026-10-08-w16.json and audit/f1/w16_decisions.tsv (deterministic).
"""
from __future__ import annotations

import collections
import glob
import json
import os
import re
from pathlib import Path

from sqlalchemy import create_engine, text

from tools.content_review import guarded_repair as gr

BATCH = "n01-source-repair-2026-10-08-w16"
ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "data/content_repairs/n01-2026-10-08-w16.json"
AUDIT = Path(__file__).resolve().parent / "audit/f1"
TSV = AUDIT / "w16_decisions.tsv"
W15 = ROOT / "data/content_repairs/n01-2026-10-07-w15-G11.json"

# ---- decisions: task -> why the current skill is a stretch -> skill_id NULL -------------------------------
_R = {
    "odz_eq": "уравнение/неравенство с показательно-степенной или смешанной структурой решается по ОДЗ и случаям, а навык «Комбинированная ОДЗ» — про область определения функции",
    "varbase_ineq": "неравенство с переменным основанием степени требует разбора случаев основания <1/>1, а не «основание больше единицы»",
    "log_trick": "олимпиадная задача на равенство двух логарифмов с разными основаниями; навык «Свойства суммы логарифмов» не её тема",
    "special": "уравнение с модулем и формулами приведения решается разбором знака cos x, это не частный случай простейшего тригонометрического уравнения",
    "double_angle": "уравнение решается многократным применением формулы двойного угла, а навык — формулы суммы и разности",
    "pacioli": "задача о справедливом разделе ставки при прерванной игре (Пачоли, Ферма); она не про умножение вероятностей независимых событий",
    "age_ineq": "текстовая задача на систему целочисленных неравенств, а не на рациональное уравнение",
    "limit_x": "вопрос о существовании предела функции x/x в точке, не лежащей в области определения; прямой подстановки здесь нет",
    "theory_sum": "теоретический вопрос (формулировка теоремы о производной суммы); навык — производные функций с корнями и дробями",
    "int_sum": "теоретический вопрос «что такое интегральная сумма»; навык — вычисление определённого интеграла",
    "motion": "дан закон движения, нужно решить квадратное уравнение x(t)=0; производной и составления закона движения нет",
    "digits": "олимпиадная задача на подсчёт цифр в записи 123456789101112…, а не на разрядный состав числа",
    "olymp_algebra": "олимпиадная задача на симметрию сумм (сумма кубов/четвёртых степеней при нулевых суммах), а не на применение ФСУ",
    "rational_roots": "рациональность корней квадратного уравнения; навык — число корней по знаку дискриминанта",
    "sampling": "репрезентативность выборки; навык «Интерпретация данных» — чтение таблиц и средние значения",
    "irrational_sin": "доказательство иррациональности sin 10° через кубическое уравнение с рациональными корнями; формулы сложения не главное",
    "induction": "шаг математической индукции для суммы кубов; навык — рекуррентные последовательности",
}
NULL_REASON: dict[str, str] = {}
def _add(key, ids):
    for i in ids:
        NULL_REASON[i] = _R[key]
_add("odz_eq", [
    "G11_TB_10_6*_10_43_1", "G11_TB_10_6*_10_43_2", "G11_TB_10_6*_10_44_1", "G11_TB_10_6*_10_44_2",
    "G11_TB_10_6*_10_45_1", "G11_TB_10_6*_10_45_2", "G11_TB_10_6*_10_45_3", "G11_TB_10_6*_10_45_4",
    "G11_TB_13_1*_12_19_a", "G11_TB_13_1*_12_19_b", "G11_TB_13_1*_12_19_в", "G11_TB_13_1*_12_19_г",
    "G11_TB_13_1*_12_23_a", "G11_TB_13_1*_12_23_б", "G11_TB_?_217_2"])
_add("varbase_ineq", ["G11_TB_§19_3_1", "G11_TB_§19_3_2"])
_add("log_trick", ["G11_TB_?_19_а", "G11_TB_?_19_б"])
_add("special", ["G11_TB_27_2_24_3"])
_add("double_angle", ["G11_TB_10_4*_22_г"])
_add("pacioli", ["G11_TB_22_6_12", "G11_TB_22_6_13"])
_add("age_ineq", ["G11_TB_27_2_90"])
_add("limit_x", ["G11_TB_§1_6"])
_add("theory_sum", ["G11_TB_§4_4_15_а"])
_add("int_sum", ["G11_TB_6_4_6_26_2"])
_add("motion", ["G11_TB_6_10*_6_89.3"])
_add("digits", ["G11_TB_?_5_б"])
_add("olymp_algebra", ["G11_TB_?_255_a", "G11_TB_?_255_b"])
_add("rational_roots", ["G11_TB_?_66", "G11_TB_?_67"])
_add("sampling", ["G11_TB_23_1_1_1", "G11_TB_23_1_1_2", "G11_TB_23_1_1_3", "G11_TB_23_1_1_4",
                  "G11_TB_23_1_1_5", "G11_TB_23_1_1_6"])
_add("irrational_sin", ["G11_TB_?_7"])
_add("induction", ["G9_TB_31_629"])

# Kept although listed as a candidate for a special reason (everything else: skill fits, sibling is only an alternative).
KEEP_SPECIAL = {
    "G11_TB_3_2*_3_6_1": "навык остался бы без задач (все 4 задачи G11_S13_01 — вопросы о взаимно обратных функциях)",
    "G11_TB_3_2*_3_6_3": "навык остался бы без задач (все 4 задачи G11_S13_01 — вопросы о взаимно обратных функциях)",
    "G11_TB_§3_3_6_а": "навык остался бы без задач (все 4 задачи G11_S13_01 — вопросы о взаимно обратных функциях)",
    "G11_TB_§3_3_6_в": "навык остался бы без задач (все 4 задачи G11_S13_01 — вопросы о взаимно обратных функциях)",
    "G11_TB_?_58_а": "навык G11_S01_02 остался бы без задач (в нём только эти 2 задачи); значение функции f(1999) действительно вычисляется",
    "G11_TB_?_58_б": "навык G11_S01_02 остался бы без задач (в нём только эти 2 задачи); значение функции f(1999) действительно вычисляется",
    "G9_TB_ЗПТ_888": "доказательство от противного оценкой 5·10^k−1 ≥ 10^k — это и есть метод оценки; навык подходит",
    "G11_TB_17_2_4_3": "log²x−4≤0 сводится к двум простейшим логарифмическим неравенствам; навык подходит",
    "G11_TB_27_2_89": "возрастная задача решается линейным уравнением по условию; текстовый навык подходит",
}
KEEP_DEFAULT = "тема навыка «%s» подходит; соседний навык — лишь альтернатива"


def candidate_ids(w15_repairs: list[dict]) -> dict[str, set[str]]:
    src: dict[str, set[str]] = collections.defaultdict(set)
    pat = re.compile(r"ближайш|nearest|no exact|олимпиад|forced|нет точного|не существует", re.I)
    for line in (AUDIT / "overrides_G11.jsonl").read_text().splitlines():
        if line.strip():
            o = json.loads(line)
            if pat.search(o.get("why", "")) or o.get("confidence", 1) < 0.7:
                src[o["id"]].add("override")
    for line in (AUDIT / "verify_G11_map.jsonl").read_text().splitlines():
        if line.strip():
            v = json.loads(line)
            if v["verdict"] == "acceptable" and re.search(r"нет\b|ближайш|отсутств|имеющ", v["reason"]):
                src[v["id"]].add("verify")
    for i in ("G9_TB_31_629", "G9_TB_ЗПТ_888"):
        src[i].add("g9")
    for r in w15_repairs:
        if re.search("набрал|заглушка", r["reason"]):
            src[r["id"]].add("stub")
    for e in json.loads((AUDIT / "new_skills_G11.json").read_text()):
        if e["decision"] == "existing":
            for p in e["proposals"]:
                for t in p.get("example_tasks", []):
                    src[t].add("gap")
    for f in sorted(glob.glob(str(AUDIT / "map_G11_part_*.jsonl"))):
        for line in open(f):
            if line.strip():
                o = json.loads(line)
                if o["to"] == "NONE" or "Олимпиад" in o.get("proposal", ""):
                    src[o["id"]].add("mapNONE")
    return src


def main() -> None:
    w15 = json.loads(W15.read_text())["repairs"]
    src = candidate_ids(w15)
    engine = create_engine(os.environ["CONTENT_REPAIR_DATABASE_URL"])
    with engine.connect() as conn:
        ids = sorted(src)
        rows = {r["id"]: r for r in gr._load(conn, ids, False)}
        names = dict(conn.execute(text("SELECT id, name_ru FROM knowledge_hierarchy")).all())
        active_count = collections.Counter(dict(conn.execute(text(
            "SELECT skill_id, count(*) FROM tasks_master WHERE is_active AND skill_id IS NOT NULL "
            "GROUP BY skill_id")).all()))
    unknown = sorted(set(NULL_REASON) - set(rows))
    if unknown:
        raise SystemExit(f"decision ids are not candidates: {unknown}")
    unknown = sorted(set(KEEP_SPECIAL) - set(rows))
    if unknown:
        raise SystemExit(f"keep ids are not candidates: {unknown}")

    decision: dict[str, tuple[str, str]] = {}
    for tid in ids:
        row = rows[tid]
        if tid in NULL_REASON:
            if row["skill_id"] is None:
                decision[tid] = ("keep", "skill_id уже NULL")
            elif row["toc_id"] is None:
                decision[tid] = ("keep", "toc_id пуст: без навыка задача не попадёт в экзамены")
            elif not row["is_active"]:
                decision[tid] = ("keep", "задача неактивна")
            else:
                decision[tid] = ("null", NULL_REASON[tid])
        else:
            decision[tid] = ("keep", KEEP_SPECIAL.get(tid) or KEEP_DEFAULT % names[row["skill_id"]])
    # no active skill may become empty
    removed = collections.Counter(rows[t]["skill_id"] for t, (d, _) in decision.items() if d == "null")
    for skill, n in removed.items():
        if active_count[skill] - n <= 0:
            for t, (d, _) in list(decision.items()):
                if d == "null" and rows[t]["skill_id"] == skill:
                    decision[t] = ("keep", f"навык {skill} остался бы без задач")
    removed = collections.Counter(rows[t]["skill_id"] for t, (d, _) in decision.items() if d == "null")
    assert all(active_count[s] - n > 0 for s, n in removed.items())

    repairs = []
    for tid in ids:
        if decision[tid][0] != "null":
            continue
        row = rows[tid]
        old = row["skill_id"]
        entry = {
            "id": tid, "before_sha256": gr.fingerprint(row),
            "reason": (f"волна w15 принудительно привязала задачу к «ближайшему» навыку «{names[old]}» ({old}), "
                       f"но он не подходит: {decision[tid][1]}; skill_id снят (задача остаётся в экзаменах через toc_id)"),
            "evidence": ("Условие задачи прочитано и сопоставлено с навыком; решение владельца 2026-10-08: навык ставится только "
                         "когда он явно подходит, иначе skill_id = NULL. toc_id задан, навык остаётся не пустым. "
                         "Меняется только skill_id; условие, ключ и дистракторы не тронуты."),
            "changes": {"skill_id": None}}
        gr.validate_entry(entry)
        entry["after_sha256"] = gr.fingerprint(gr.candidate(row, entry, BATCH))
        repairs.append(entry)
    manifest = {"batch": BATCH, "mode": "in_place_owner_requested", "source_checked_at": "2026-10-08T00:00:00Z",
                "student_data_included": False, "repairs": repairs}
    OUT.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    lines = ["id\tcurrent_skill\tdecision\treason"]
    for tid in ids:
        d, why = decision[tid]
        lines.append(f"{tid}\t{rows[tid]['skill_id']}\t{d}\t{why}")
    TSV.write_text("\n".join(lines) + "\n")
    print(OUT, "candidates", len(ids), "null", len(repairs), "keep", len(ids) - len(repairs))


if __name__ == "__main__":
    main()
