"""Build manifest n01-2026-10-06-w8: leftover sub-item labels + percent word-problem skill remaps.

Reads the local DB only; never writes to it. Usage (from content-service):
  CONTENT_REPAIR_DATABASE_URL=... python3 -m tools.content_review.build_w8_labels [--colon-only]

Part 1: a single question split from a textbook batch still carries one sub-item label
("б) ", "1) ") right after the colon (or, for letters, at the very start of the text).
The label is removed from question_text AND question_latex, only when the text outside
$...$ contains exactly one label candidate and question_latex agrees. Texts with two or
more label candidates may be genuine multi-part tasks and are skipped.
Part 2: percent/price word problems sitting under probability skills G9_S35_* are remapped.
"""
from __future__ import annotations

import json
import os
import random
import re
import sys
from pathlib import Path

from sqlalchemy import create_engine

from tools.content_review import guarded_repair as gr

BATCH = "n01-source-repair-2026-10-06-w8"
OUT = Path(__file__).resolve().parents[2] / "data/content_repairs/n01-2026-10-06-w8.json"

MATH = re.compile(r"\$\$[\s\S]+?\$\$|\$[^$]+?\$")
# label candidate: letter or 1-2 digits + ")" preceded by text start / whitespace / :;,. and followed by whitespace/end
CAND = re.compile(r"(?<![^\s:;,.])([а-яёa-z]|\d{1,2})\)(?=\s|$)")

SKILL_FIXES = {
    "G9_TB_5_64": (
        "G5_S46_02",
        "навык G9_S35_04 («Вытаскивание шара из урны», вероятность) не соответствует задаче: это текстовая "
        "задача на скидку 20% и цены (процент от числа, деление с остатком), вероятности в ней нет",
        "500 / 26,5 = 18,87 -> 18 тетрадей; цена в гипермаркете 26,5 * 0,8 = 21,2 р., 500 / 21,2 = 23,58 -> 23 "
        "тетради; 23 - 18 = 5 (ключ $5$ верен). Задача о скидке на цену товара; в банке подходящие навыки "
        "по процентам есть только в 5 классе: G5_S46_02 «Скидки и наценки» (раздел G5_P46 «Задачи с "
        "экономическим содержанием»; прецедент: G10_TB_3_9_9 про скидки отнесена к G5_S46_02) и "
        "G5_S40_02 «Нахождение процента от числа». Вероятностного содержания нет."),
    "G9_TB_5_65": (
        "G5_S46_02",
        "навык G9_S35_01 («Классическая вероятность») не соответствует задаче: это выбор наиболее выгодной "
        "даты покупки при разных скидках, вероятности в ней нет",
        "Холодильник 45000 * 0,9 = 40500 (25-28 февраля), стиральная машина 22000 * 0,7 = 15400 (1-15 марта); "
        "сумма 55900 совпадает с ключом. Задача целиком про скидки в процентах: G5_S46_02 «Скидки и наценки»."),
    "G9_TB_5_69": (
        "G5_S46_02",
        "навык G9_S35_05 («Свойства вероятности») не соответствует задаче: это снижение цены на 10% и "
        "обратное повышение, вероятности в ней нет",
        "Цена x снижена до 0,9x; чтобы вернуться к x, нужно повысить на (x - 0,9x) / 0,9x = 1/9 = 11 1/9 % "
        "(ключ верен). Задача про скидки/наценки в процентах: G5_S46_02 «Скидки и наценки»."),
}


def mask(text: str) -> str:
    return MATH.sub(lambda m: "\x00" * len(m.group(0)), text)


def candidates(text: str) -> list[re.Match]:
    return list(CAND.finditer(mask(text)))


def classify(text: str, m: re.Match) -> str | None:
    """'colon' (after ':'), 'leading' (letter at text start) or None."""
    before = text[:m.start()]
    if before.rstrip(" \t\n").endswith(":"):
        return "colon"
    if before.strip() == "" and not m.group(1).isdigit():
        return "leading"
    return None


def remove_label(text: str, m: re.Match) -> str:
    pre, post = text[:m.start()], text[m.end():]
    post_stripped = post.lstrip(" \t")
    if post_stripped.startswith("\n"):
        pre = pre.rstrip(" \t")
        post = post_stripped[1:] if (pre == "" or pre.endswith("\n")) else post_stripped
    else:
        post = post_stripped
        if pre.endswith(":") and post:
            pre += " "
    new = pre + post
    stripped = new.rstrip()
    if stripped and mask(stripped)[-1] in ";,":
        new = stripped[:-1].rstrip()
    return new


def plan(row: dict, colon_only: bool):
    """Return ('fix', info) | ('multi', cands) | ('skip', reason) | None (no label in scope)."""
    t, lt = row["question_text"] or "", row["question_latex"] or ""
    cands = candidates(t)
    kinds = [classify(t, c) for c in cands]
    allowed = ("colon",) if colon_only else ("colon", "leading")
    if not any(k in allowed for k in kinds):
        return None
    if len(cands) >= 2:
        return "multi", [c.group(0) for c in cands]
    m, kind = cands[0], kinds[0]
    if not lt:
        return "skip", "нет question_latex"
    lc = candidates(lt)
    if not lc:
        return "skip", "question_latex уже без метки (метка только в question_text)"
    if len(lc) != 1 or lc[0].group(0) != m.group(0) or classify(lt, lc[0]) != kind:
        return "skip", "метка в question_latex отличается от question_text"
    return "fix", {"label": m.group(0), "kind": kind,
                   "new_text": remove_label(t, m), "new_latex": remove_label(lt, lc[0])}


def validate_fix(row: dict, info: dict) -> str | None:
    for field, new in (("question_text", info["new_text"]), ("question_latex", info["new_latex"])):
        old = row[field]
        if len(new) < 10:
            return f"{field}: короче 10 символов"
        if new.count("$") % 2:
            return f"{field}: нечётное число $"
        if new.rstrip().endswith(":"):
            return f"{field}: после удаления метки не осталось условия"
        if candidates(new) and classify(new, candidates(new)[0]):
            return f"{field}: новый текст начинается с метки"
        if len(candidates(old)) != 1:
            return f"{field}: метка в оригинале не единственная"
        if old.count("$") % 2:
            return f"{field}: нечётное число $ уже в оригинале"
    return None


def entry(row: dict, changes: dict, reason: str, evidence: str) -> dict:
    e = {"id": row["id"], "before_sha256": gr.fingerprint(row), "reason": reason,
         "evidence": evidence, "changes": changes}
    gr.validate_entry(e)
    after = gr.candidate(row, e, BATCH)
    e["after_sha256"] = gr.fingerprint(after)
    return e


def main() -> None:
    colon_only = "--colon-only" in sys.argv
    engine = create_engine(os.environ["CONTENT_REPAIR_DATABASE_URL"])
    from sqlalchemy import text
    with engine.connect() as conn:
        ids = [r[0] for r in conn.execute(text(
            "SELECT id FROM tasks_master WHERE is_active AND question_text ~ '[а-яёa-z0-9]\\)' ORDER BY id"))]
        rows = []
        for i in range(0, len(ids), 500):
            rows += gr._load(conn, ids[i:i + 500], False)
        skill_rows = {r["id"]: r for r in gr._load(conn, list(SKILL_FIXES), False)}
        valid_skills = {r[0] for r in conn.execute(text(
            "SELECT id FROM knowledge_hierarchy WHERE is_active"))}
    fixes, multi, skipped, invalid = [], [], [], []
    for row in rows:
        res = plan(row, colon_only)
        if res is None:
            continue
        kind, data = res
        if kind == "multi":
            multi.append((row, data))
        elif kind == "skip":
            skipped.append((row, data))
        else:
            err = validate_fix(row, data)
            (invalid if err else fixes).append((row, data, err))
    repairs, by_id = [], {}
    for row, info, _ in fixes:
        label = info["label"]
        trailing = mask(row["question_text"].rstrip())[-1:] in (";", ",")
        changes = {"question_text": info["new_text"], "question_latex": info["new_latex"]}
        reason = f"убрана метка подпункта «{label}» из условия одиночной задачи"
        evidence = (f"Одиночная задача из учебного набора сохранила ровно одну метку подпункта «{label}» "
                    f"({'после двоеточия' if info['kind'] == 'colon' else 'в начале условия'}); вне формул "
                    "других меток нет, в question_text и question_latex метка совпадает. Удалена метка"
                    + (" и висячий знак «;»/«,» в конце" if trailing else "")
                    + "; формулы, ответ и варианты не менялись.")
        by_id[row["id"]] = (row, changes, reason, evidence)
    for tid, (skill, reason_core, evidence) in SKILL_FIXES.items():
        assert skill in valid_skills, skill
        row = skill_rows[tid]
        assert row["is_active"]
        reason = f"неверное отображение навыка: {reason_core}"
        if tid in by_id:
            r0, ch, rs, ev = by_id[tid]
            by_id[tid] = (r0, {**ch, "skill_id": skill}, rs + "; " + reason, ev + " " + evidence)
        else:
            by_id[tid] = (row, {"skill_id": skill}, reason, evidence)
    for tid in sorted(by_id):
        row, changes, reason, evidence = by_id[tid]
        repairs.append(entry(row, changes, reason, evidence))
    manifest = {"batch": BATCH, "mode": "in_place_owner_requested",
                "source_checked_at": "2026-10-06T00:00:00Z", "student_data_included": False,
                "repairs": repairs}
    OUT.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    print(OUT)
    print(f"label fixes: {len(fixes)}; skill fixes: {len(SKILL_FIXES)}; manifest entries: {len(repairs)}")
    print(f"skipped multi-label: {len(multi)}; skipped other: {len(skipped)}; invalid after check: {len(invalid)}")
    for row, labels in multi[:10]:
        print("  MULTI", row["id"], labels, repr(row["question_text"][:110]))
    for row, why in skipped[:10]:
        print("  SKIP ", row["id"], why, repr(row["question_text"][:90]))
    for row, info, err in invalid[:10]:
        print("  INVALID", row["id"], err, repr(row["question_text"][:90]))
    random.seed(8)
    print("random before -> after:")
    for row, info, _ in random.sample(fixes, min(15, len(fixes))):
        print(" ", row["id"], repr(row["question_text"][:95]), "->", repr(info["new_text"][:95]))
    # side files for validation scripts
    scratch = os.environ.get("W8_SCRATCH")
    if scratch:
        Path(scratch, "w8_latex.json").write_text(json.dumps(
            {row["id"]: [info["new_latex"]] for row, info, _ in fixes}, ensure_ascii=False))
        Path(scratch, "w8_multi.json").write_text(json.dumps(
            [[r["id"], l] for r, l in multi], ensure_ascii=False))
        Path(scratch, "w8_skipped.json").write_text(json.dumps(
            [[r["id"], w] for r, w in skipped] + [[r["id"], e] for r, _, e in invalid], ensure_ascii=False))


if __name__ == "__main__":
    main()
