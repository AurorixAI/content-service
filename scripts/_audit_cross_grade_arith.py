#!/usr/bin/env python3
import re, sys
sys.path.insert(0, "/app")
from decimal import Decimal
from sqlalchemy import create_engine, text
from src.core.config import get_settings


def last_arith_line(q):
    lines = [l.strip() for l in (q or "").splitlines() if l.strip()]
    for line in reversed(lines):
        line2 = line.replace("×", "*").replace("÷", "/")
        if re.fullmatch(r"[\d\s,\.\+\-\*/\(\)]+", line2) and re.search(r"[\+\-\*/]", line2):
            return line2.replace(" ", "").replace(",", ".")
    return None


def compute(e):
    if not e or not re.fullmatch(r"[\d\.\+\-\*/\(\)]+", e):
        return None
    try:
        return Decimal(str(eval(e, {"__builtins__": {}})))
    except Exception:
        return None


def audit_level(level: int) -> dict:
    e = create_engine(get_settings().database_url)
    with e.connect() as c:
        total = c.execute(
            text(
                """
                SELECT count(*) FROM tasks_master tm
                JOIN textbook_toc toc ON toc.id = tm.toc_id
                JOIN textbooks tb ON tb.textbook_id = toc.textbook_id
                WHERE tb.class_level = :l AND tm.verification_status = 'verified'
                """
            ),
            {"l": level},
        ).scalar()
        text_route = c.execute(
            text(
                """
                SELECT count(*) FROM tasks_master tm
                JOIN textbook_toc toc ON toc.id = tm.toc_id
                JOIN textbooks tb ON tb.textbook_id = toc.textbook_id
                WHERE tb.class_level = :l AND tm.tags->>'smart_verify_route' = 'text'
                """
            ),
            {"l": level},
        ).scalar()
        split_child = c.execute(
            text(
                """
                SELECT count(*) FROM tasks_master tm
                JOIN textbook_toc toc ON toc.id = tm.toc_id
                JOIN textbooks tb ON tb.textbook_id = toc.textbook_id
                WHERE tb.class_level = :l AND tm.tags ? 'split_from'
                """
            ),
            {"l": level},
        ).scalar()
        rows = c.execute(
            text(
                """
                SELECT tm.question_text, tm.correct_answer
                FROM tasks_master tm
                JOIN textbook_toc toc ON toc.id = tm.toc_id
                JOIN textbooks tb ON tb.textbook_id = toc.textbook_id
                WHERE tb.class_level = :l AND tm.answer_type = 'text'
                  AND tm.question_text ILIKE '%выполните действ%'
                """
            ),
            {"l": level},
        ).fetchall()
    bad = checked = 0
    for r in rows:
        ex = last_arith_line(r.question_text)
        if not ex:
            continue
        comp = compute(ex)
        if comp is None:
            continue
        checked += 1
        try:
            ast = Decimal((r.correct_answer or "").strip().replace(" ", "").replace(",", "."))
        except Exception:
            continue
        if abs(comp - ast) > Decimal("0.0001"):
            bad += 1
    return {
        "level": level,
        "verified": total,
        "text_route": text_route,
        "split_children": split_child,
        "arith_checked": checked,
        "arith_bad": bad,
    }


if __name__ == "__main__":
    for l in [5, 6, 7, 8]:
        print(audit_level(l))
