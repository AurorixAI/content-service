"""Build manifest n01-2026-10-07-w14 (skill mis-mappings, skill_id only). Reads the local DB only.

1. Tasks about complex numbers sitting under unrelated active skills G11_S01_01/02/03 / G11_S06_*:
   the complex subtree (G11_COMPLEX/T07/P45/S45_*) is inactive and no other active skill covers
   complex numbers, so skill_id -> NULL (exam-only by project policy, still usable in exams).
   If an active complex skill ever exists, set COMPLEX_TARGET to its id.
2. A short list of obvious non-complex mis-mappings is remapped to existing active skills.

Usage (from content-service):
  CONTENT_REPAIR_DATABASE_URL=... python3 -m tools.content_review.build_w14_complex_skill
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

from sqlalchemy import create_engine, text

from tools.content_review import guarded_repair as gr

BATCH = "n01-source-repair-2026-10-07-w14"
OUT = Path(__file__).resolve().parents[2] / "data/content_repairs/n01-2026-10-07-w14.json"
COMPLEX_TARGET = None  # no active complex-number skill exists (all of G11_COMPLEX is inactive)

STRONG = re.compile(
    r"комплекс|мним|i\^\{?2|e\^\{?-?\d*i|\\bar\s*\{?z|\\overline\{?[uvz]|z̄|ū|"
    r"\\operatorname\{Re\}|\bRe\s*z|\bIm\s*z|\\?arg\s*z|\|z")
IMAG = re.compile(r"(?<![A-Za-zА-Яа-я\\_^{])i(?![A-Za-z_])")

# (task id, new skill, why)
REMAP = [
    ("G11_TB_21_1_2_2", "G7_S37_01", "7 учреждений, число маршрутов = 7! (перестановки)"),
    ("G11_TB_21_1_2_4", "G7_S37_01", "порядок трёх цифр, 3! = 6 (перестановки)"),
    ("G11_TB_21_1_2_5_1", "G7_S37_01", "шестизначные числа из шести разных цифр, 6! = 720"),
    ("G11_TB_21_1_1_1*", "G8_S31_01", "4 конверта × 3 марки, правило произведения"),
    ("G11_TB_21_1_3_21_4", "G7_S37_03", "уравнение с числом сочетаний C(x,3), C(x+2,4)"),
    ("G11_TB_22_1_14", "G10_S28_01", "лотерея 100 билетов, 5 выигрышных: классическая вероятность"),
    ("G11_TB_22_2_22_2", "G10_S28_01", "карандаши в ящике: классическая вероятность"),
    ("G11_TB_§15_1_5", "G10_S16_01", "log_{1/2}8 = -3 по определению логарифма"),
    ("G11_TB_§15_7_3", "G10_S17_01", "log_5 30 = 1 + log_5 2 + log_5 3 (свойства логарифмов)"),
    ("G11_TB_27_2_8_1", "G10_S25_03", "sin2x = √3 cos x: разложение на множители"),
    ("G11_TB_27_2_8_2", "G10_S25_03", "sin2x = √2 cos x: разложение на множители"),
    ("G11_TB_27_2_13_2", "G10_S25_01", "cos2x = sin x: замена t = sin x"),
    ("G11_TB_14_1_1_7", "G10_S14_01", "4^x = 2^{6+x-x²}: приведение к общему основанию"),
    ("G11_TB_14_2_2_3", "G10_S14_04", "2^x + 2^{2-x} = 5: замена t = 2^x"),
    ("G11_TB_14_3_1_6", "G10_S15_02", "показательное неравенство, основание 1/2 < 1"),
    ("G11_TB_14_3_1_8", "G10_S15_02", "показательное неравенство, основание 1/4 < 1"),
]
SRC = ("G11_S01_02",)

# Other active G11 skills (outside S01/S06): strict text match, reviewed by hand (47 hits, all complex
# numbers), plus two answer-only cases found by the imaginary-unit scan.
STRICT = re.compile(
    r"комплекс|мним|\\bar\s*\{?z|z̄|ū|\\operatorname\{Re\}|\bRe\s*z|\bIm\s*z|\barg\s*z|"
    r"(?<![A-Za-zА-Яа-я\\_^{])i\^\{?\d|(?<![A-Za-zА-Яа-я\\_^{])e\^\{?-?\d*i\\?(pi|π|\\varphi|φ)|"
    r"\d\s*i(?![A-Za-z_\d])|[+-]\s*i(?![A-Za-z_\d])")
EXTRA_IDS = ("G11_TB_18_2*_18_3_е", "G11_TB_18_1*_17_26_3")


def is_complex(row: dict) -> bool:
    t, a = row["question_text"] or "", row["correct_answer"] or ""
    return bool(STRONG.search(t) or IMAG.search(t) or IMAG.search(a))


def entry(row: dict, skill, reason: str, evidence: str) -> dict:
    e = {"id": row["id"], "before_sha256": gr.fingerprint(row), "reason": reason,
         "evidence": evidence, "changes": {"skill_id": skill}}
    gr.validate_entry(e)
    e["after_sha256"] = gr.fingerprint(gr.candidate(row, e, BATCH))
    return e


def main() -> None:
    engine = create_engine(os.environ["CONTENT_REPAIR_DATABASE_URL"])
    with engine.connect() as conn:
        ids = [r[0] for r in conn.execute(text(
            "SELECT id FROM tasks_master WHERE is_active AND (skill_id LIKE 'G11\\_S01\\_%' "
            "OR skill_id LIKE 'G11\\_S06\\_%') ORDER BY id"))]
        other = [r[0] for r in conn.execute(text(
            "SELECT t.id, t.question_text FROM tasks_master t JOIN knowledge_hierarchy k ON k.id = t.skill_id "
            "WHERE t.is_active AND k.is_active AND t.skill_id LIKE 'G11\\_%' "
            "AND t.skill_id NOT LIKE 'G11\\_S01\\_%' AND t.skill_id NOT LIKE 'G11\\_S06\\_%' ORDER BY t.id"))
            if STRICT.search(r[1] or "")]
        other = sorted(set(other) | set(EXTRA_IDS))
        ids = sorted(set(ids) | set(other))
        rows = {r["id"]: r for r in gr._load(conn, ids, False)}
        skills = {r[0]: r[1] for r in conn.execute(text(
            "SELECT id, is_active FROM knowledge_hierarchy WHERE id = ANY(:i)"),
            {"i": [s for _, s, _ in REMAP] + ([COMPLEX_TARGET] if COMPLEX_TARGET else [])})}
    if COMPLEX_TARGET and not skills.get(COMPLEX_TARGET):
        raise SystemExit("complex target skill is not active")
    for _, s, _ in REMAP:
        if not skills.get(s):
            raise SystemExit(f"remap target {s} is missing or inactive")
    remap_ids = {i for i, _, _ in REMAP}
    repairs = []
    for tid in sorted(ids):
        row = rows[tid]
        if tid in remap_ids or not (tid in other or is_complex(row)):
            continue
        old = row["skill_id"]
        dest = COMPLEX_TARGET
        repairs.append(entry(
            row, dest,
            f"задача по комплексным числам стоит под несвязанным навыком {old}; поддерево "
            "G11_COMPLEX неактивно и активного навыка по комплексным числам нет, поэтому "
            "отчёт диагностики ошибочно приписывал ученику слабость в «" + (
                "вычислении значения функции" if old == "G11_S01_02" else "теме навыка " + old) +
            "»; skill_id снят (задача только для экзаменов по политике проекта)",
            "Условие/ответ содержат мнимую единицу i, комплексные числа, тригонометрическую/"
            "показательную форму, сопряжение или аргумент (проверено автоматическим разбором "
            "текста и просмотром сомнительных случаев вручную); навыки G11_COMPLEX, G11_T07, "
            "G11_P45, G11_S45_* is_active = false; активных навыков по комплексным числам в "
            "иерархии нет (G10_S06_08 — преобразования графиков, G9_S38_05 — статистика). "
            "Меняется только skill_id; условие, ключ и дистракторы не тронуты."))
    for tid, new, why in REMAP:
        row = rows[tid]
        if row["skill_id"] not in SRC:
            raise SystemExit(f"{tid}: unexpected source skill {row['skill_id']}")
        repairs.append(entry(
            row, new,
            f"явная неверная привязка: задача не про вычисление значения функции ({why}); "
            f"перенос с {row['skill_id']} на {new}",
            f"Содержание задачи прочитано: {why}. Целевой навык существует и активен. "
            "Меняется только skill_id; условие, ключ и дистракторы не тронуты."))
    manifest = {"batch": BATCH, "mode": "in_place_owner_requested",
                "source_checked_at": "2026-10-07T00:00:00Z", "student_data_included": False,
                "repairs": repairs}
    OUT.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    n_null = sum(1 for r in repairs if r["changes"]["skill_id"] is None)
    print(OUT, "total", len(repairs), "null", n_null, "remap", len(repairs) - n_null)


if __name__ == "__main__":
    main()
