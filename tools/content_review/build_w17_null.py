"""Build data/content_repairs/n01-2026-10-08-w17-null.json: skill_id -> NULL for 6 stretch tasks that were kept
under G11_S01_02 / G11_S13_01 only so the skills would not be empty. Apply AFTER the w17 insert manifest
(n01-2026-10-08-w17-new-tasks.json). Reads the local DB only.
  CONTENT_REPAIR_DATABASE_URL=... python3 -m tools.content_review.build_w17_null
"""
import json
import os
from pathlib import Path

from sqlalchemy import create_engine

from tools.content_review import guarded_repair as gr

BATCH = "n01-source-repair-2026-10-08-w17-null"
OUT = Path(__file__).resolve().parents[2] / "data/content_repairs/n01-2026-10-08-w17-null.json"
IDS = {
    "G11_TB_3_2*_3_6_1": ("G11_S13_01", "теоретический вопрос «какие функции называют взаимно обратными, их свойства»: определение и свойства, а не нахождение значения обратной функции"),
    "G11_TB_§3_3_6_а": ("G11_S13_01", "теоретический вопрос «какие функции называют взаимно обратными, их свойства»: определение и свойства, а не нахождение значения обратной функции"),
    "G11_TB_3_2*_3_6_3": ("G11_S13_01", "теоретический вопрос о достаточном условии существования обратной функции (строгая монотонность), а не о значении обратной функции"),
    "G11_TB_§3_3_6_в": ("G11_S13_01", "теоретический вопрос о достаточном условии существования обратной функции (строгая монотонность), а не о значении обратной функции"),
    "G11_TB_?_58_а": ("G11_S01_02", "значение f(1999) находится из функционального равенства f((a+2b)/3)=(f(a)+2f(b))/3 по двум известным значениям, а не вычислением по заданной формуле функции"),
    "G11_TB_?_58_б": ("G11_S01_02", "значение f(1999) находится из функционального равенства f((a+2b)/3)=(f(a)+2f(b))/3 по двум известным значениям, а не вычислением по заданной формуле функции"),
}


def main():
    engine = create_engine(os.environ["CONTENT_REPAIR_DATABASE_URL"])
    with engine.connect() as conn:
        rows = {r["id"]: r for r in gr._load(conn, sorted(IDS), False)}
    repairs = []
    for tid in sorted(IDS):
        skill, why = IDS[tid]
        r = rows[tid]
        assert r["skill_id"] == skill and r["is_active"] and r["toc_id"] is not None, (tid, r["skill_id"], r["toc_id"])
        e = {"id": tid, "before_sha256": gr.fingerprint(r), "changes": {"skill_id": None},
             "reason": f"задача держалась под навыком {skill} только чтобы навык не был пустым; по содержанию это не его тип: {why}. "
                       "После добавления 7 настоящих задач навыка (n01-2026-10-08-w17-new-tasks) привязка не нужна; skill_id снят "
                       "(задача остаётся для экзаменов и в учебнике по toc_id)",
             "evidence": f"Условие и ключ прочитаны; toc_id={r['toc_id']} сохраняется (раздел учебника не теряется). "
                         "Целевая подгонка отсутствует: меняется только skill_id; условие, ключ, дистракторы не тронуты."}
        gr.validate_entry(e)
        e["after_sha256"] = gr.fingerprint(gr.candidate(r, e, BATCH))
        repairs.append(e)
    m = {"batch": BATCH, "mode": "in_place_owner_requested", "source_checked_at": "2026-10-08T00:00:00Z",
         "student_data_included": False, "apply_after": "n01-2026-10-08-w17-new-tasks.json", "repairs": repairs}
    OUT.write_text(json.dumps(m, ensure_ascii=False, indent=2) + "\n")
    print(OUT, len(repairs), "repairs; toc_ids", sorted({r["toc_id"] for r in rows.values()}))


if __name__ == "__main__":
    main()
