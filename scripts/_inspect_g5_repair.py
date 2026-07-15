#!/usr/bin/env python3
import sys
sys.path.insert(0, "/app")
from sqlalchemy import create_engine, text
from src.core.config import get_settings
from src.pipeline.compound_detect import detect_compound

e = create_engine(get_settings().database_url)
ids = ["G5_TB_6_202", "G5_TB_39_679"]
with e.connect() as c:
    for tid in ids:
        r = c.execute(
            text("""
                SELECT tm.id, tm.question_text, tm.correct_answer, tm.answer_type, tm.tags
                FROM tasks_master tm WHERE tm.id = :id
            """),
            {"id": tid},
        ).first()
        print("=" * 70, tid)
        print("Q:\n", r.question_text)
        print("A:", r.correct_answer)
        tags = r.tags or {}
        for k in sorted(tags):
            if any(x in k for x in ("compound", "split", "repair", "verify", "content")):
                print(f"  {k}: {tags[k]}")
        ch = c.execute(
            text("SELECT id, correct_answer FROM tasks_master WHERE tags->>'split_from' = :id ORDER BY id"),
            {"id": tid},
        ).fetchall()
        print("children:", len(ch))
        for x in ch:
            print(" ", x.id, "|", x.correct_answer)
        comp = detect_compound(
            task_id=tid,
            question_text=r.question_text or "",
            correct_answer=r.correct_answer or "",
            answer_type=r.answer_type or "",
            tags=tags,
        )
        print("detect:", comp.pattern, "should_split=", comp.should_split, "exam_unsafe=", comp.exam_unsafe)
        if comp.warning:
            print("warning:", comp.warning[:200])
