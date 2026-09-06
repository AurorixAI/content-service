#!/usr/bin/env python3
import sys
sys.path.insert(0, "/app")
from sqlalchemy import create_engine, text
from src.core.config import get_settings

CRITICAL = [
    "G5_TB_13_245", "G5_TB_13_247", "G5_TB_21_844", "G5_TB_25_987",
    "G5_TB_44_1718.4", "G5_TB_67_1642", "G5_TB_4_66", "G5_TB_10_386.2",
    "G5_TB_41_726", "G5_TB_55_1292",
]
e = create_engine(get_settings().database_url)
with e.connect() as c:
    for tid in CRITICAL:
        r = c.execute(
            text("""
                SELECT question_text, correct_answer,
                       tags->>'answer_gemini_candidate' AS cand
                FROM tasks_master WHERE id = :id
            """),
            {"id": tid},
        ).first()
        print("===", tid)
        print((r.question_text or "")[:400])
        print("A:", r.correct_answer)
        print("LLM:", r.cand)
        print()
