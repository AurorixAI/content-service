"""
Content Service — Read API

Exposes content-DB data (skills, tasks, textbooks) to other microservices
via HTTP so they never need a direct Postgres connection to content-db.

All routes are read-only (SELECT only).  No auth required — network-level
isolation (Docker internal network) is the access control.

Prefix: /api/v1/content
"""
from __future__ import annotations

import re
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.engine import Connection

from src.core.database import get_db

router = APIRouter(prefix="/api/v1/content", tags=["Content Read API"])

# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────

_SKILL_COLS = """
    id, level, parent_id, name_ru, description,
    class_level_start, class_level_end, sequence_order,
    importance, cognitive_type, is_active,
    example_task, assessed_ability, difficulty_level, formula
"""

_TASK_COLS = """
    tm.id, tm.skill_id, COALESCE(kh.name_ru, '') AS skill_name,
    tm.difficulty, tm.question_text, tm.question_latex,
    tm.answer_type, tm.correct_answer, tm.correct_answer_latex,
    tm.answer_options, tm.distractor_meta,
    tm.irt_discrimination, tm.irt_difficulty, tm.irt_guessing
"""

_RE_FIGURE      = re.compile(r'\[FIGURE\s+id=["\'][^"\']*["\']\]', re.I)
_RE_MARKERS     = re.compile(r'[★●◆▲►•◉]')
_RE_SUBPOINT    = re.compile(r'^\s*(?:\d+|[а-яёa-z])[).\s]\s*', re.I)


def _clean_text(s: str | None) -> str:
    """
    Очешено:
    - [FIGURE id="..."] маркеры
    - макреы с учебника (★ ● ◆ …)
    - Указатели перед примерами (1), а), б))
    """
    if not s:
        return ""
    s = _RE_FIGURE.sub("", s)
    s = _RE_MARKERS.sub("", s)
    s = _RE_SUBPOINT.sub("", s)
    # Убирание лишних пробелов и пустых строк
    s = re.sub(r'[ \t]{2,}', ' ', s)
    s = re.sub(r'\n{3,}', '\n\n', s)
    return s.strip()


def _skill_row(r) -> dict:
    return {
        "id": r[0], "level": r[1], "parent_id": r[2], "name_ru": r[3],
        "description": r[4], "class_level_start": r[5], "class_level_end": r[6],
        "sequence_order": r[7] or 0, "importance": r[8] or 5,
        "cognitive_type": r[9], "is_active": bool(r[10]),
        "example_task": _clean_text(r[11]), "assessed_ability": r[12],
        "difficulty_level": r[13], "formula": r[14],
    }


def _task_row(r) -> dict:
    return _task_row_full(r)


def _task_row_full(r) -> dict:
    """Same as _task_row but uses correct column offsets."""
    return {
        "id": r[0],
        "task_id": r[0],
        "skill_id": r[1] or "",
        "skill_name": r[2] or "",
        "difficulty": r[3] or "B",
        "question_text": _clean_text(r[4]),
        "question_latex": r[5],
        "answer_type": r[6] or "exact_number",
        "correct_answer": _clean_text(r[7]),
        "correct_answer_latex": r[8] or "",
        "answer_options": [_clean_text(opt) if isinstance(opt, str) else opt for opt in r[9]] if isinstance(r[9], list) else r[9],
        "distractor_meta": r[10],
        "irt_discrimination": float(r[11] or 1.0),
        "irt_difficulty": float(r[12] or 0.0),
        "irt_guessing": float(r[13] or 0.0),
    }


# ──────────────────────────────────────────────────────────────────────────────
# Skills  (knowledge_hierarchy)
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/skills/{skill_id}", summary="Get a single skill node")
def get_skill(skill_id: str, conn: Connection = Depends(get_db)):
    row = conn.execute(
        text(f"SELECT {_SKILL_COLS} FROM knowledge_hierarchy WHERE id = :id"),
        {"id": skill_id},
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"Skill {skill_id!r} not found")
    return _skill_row(row)


@router.get("/skills/{skill_id}/children", summary="Direct children of a skill node")
def get_children(skill_id: str, conn: Connection = Depends(get_db)):
    rows = conn.execute(
        text(f"""
            SELECT {_SKILL_COLS}
            FROM knowledge_hierarchy
            WHERE parent_id = :parent_id AND is_active = TRUE
            ORDER BY sequence_order
        """),
        {"parent_id": skill_id},
    ).fetchall()
    return [_skill_row(r) for r in rows]


@router.get("/skills/{skill_id}/prerequisites", summary="Prerequisites for a skill")
def get_prerequisites(
    skill_id: str,
    hard_only: bool = False,
    conn: Connection = Depends(get_db),
):
    q = """
        SELECT skill_id, prerequisite_id, weight, dependency_type, criticality
        FROM skill_prerequisites
        WHERE skill_id = :skill_id
    """
    params: dict = {"skill_id": skill_id}
    if hard_only:
        q += " AND dependency_type = 'hard'"
    q += " ORDER BY weight DESC"
    rows = conn.execute(text(q), params).fetchall()
    return [
        {
            "skill_id": r[0], "prerequisite_id": r[1],
            "weight": float(r[2] or 1.0), "dependency_type": r[3] or "hard",
            "criticality": r[4] or 5,
        }
        for r in rows
    ]


@router.get("/skills", summary="Skill tree or filtered list")
def get_skills(
    level: Optional[str] = None,
    grade: Optional[int] = None,
    class_level: Optional[int] = None,
    with_task_counts: bool = False,
    conn: Connection = Depends(get_db),
):
    """
    Returns knowledge_hierarchy nodes.

    - ``level`` + ``grade``   — filter by level (L1/L2/L3/L4) and grade year
    - ``class_level``         — skill tree for a school year (with task counts)
    - no params               — full active tree
    """
    if with_task_counts or class_level is not None:
        # Skill tree with task counts (used by exam-service)
        q = """
            SELECT kh.id, kh.level, kh.name_ru, kh.parent_id,
                   kh.class_level_start, kh.class_level_end,
                   kh.importance, kh.sequence_order,
                   COUNT(tm.id) AS tasks_count
            FROM knowledge_hierarchy kh
            LEFT JOIN tasks_master tm ON tm.skill_id = kh.id AND tm.is_active = TRUE
            WHERE kh.is_active = TRUE
        """
        params: dict = {}
        if class_level:
            q += (
                " AND (kh.class_level_start IS NULL OR kh.class_level_start <= :cl)"
                " AND (kh.class_level_end   IS NULL OR kh.class_level_end   >= :cl)"
            )
            params["cl"] = class_level
        q += " GROUP BY kh.id ORDER BY kh.sequence_order"
        rows = conn.execute(text(q), params).fetchall()
        return [
            {
                "id": r[0], "level": r[1], "name_ru": r[2] or "",
                "parent_id": r[3],
                "class_level_start": r[4], "class_level_end": r[5],
                "importance": r[6] or 5, "sequence_order": r[7] or 0,
                "tasks_count": r[8],
            }
            for r in rows
        ]

    # Filtered list (used by diagnostic-service)
    q = f"SELECT {_SKILL_COLS} FROM knowledge_hierarchy WHERE is_active = TRUE"
    params = {}
    if level:
        q += " AND level = :level"
        params["level"] = level
    if grade is not None:
        q += " AND class_level_start <= :grade AND class_level_end >= :grade"
        params["grade"] = grade
    q += " ORDER BY sequence_order"
    rows = conn.execute(text(q), params).fetchall()
    return [_skill_row(r) for r in rows]


# ──────────────────────────────────────────────────────────────────────────────
# Tasks  (tasks_master)
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/tasks/{task_id}", summary="Get a single task (full fields)")
def get_task(task_id: str, conn: Connection = Depends(get_db)):
    row = conn.execute(
        text(f"""
            SELECT {_TASK_COLS}
            FROM tasks_master tm
            LEFT JOIN knowledge_hierarchy kh ON kh.id = tm.skill_id
            WHERE tm.id = :id
        """),
        {"id": task_id},
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"Task {task_id!r} not found")
    return _task_row_full(row)


@router.get("/tasks", summary="Filter tasks by skill_id(s), toc_ids, or textbook")
def list_tasks(
    skill_id: Optional[str] = None,
    skill_ids: List[str] = Query(default=[]),
    toc_ids: List[int] = Query(default=[]),
    textbook_id: Optional[str] = None,
    difficulty: Optional[str] = None,
    limit: int = Query(default=20, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    exclude_ids: List[str] = Query(default=[]),
    random_order: bool = False,
    conn: Connection = Depends(get_db),
):
    """
    Returns a list of tasks.  Exactly one filter group should be provided:

    - ``skill_id``   — single skill (diagnostic-service)
    - ``skill_ids``  — multiple skills (exam-service)
    - ``toc_ids``    — by table-of-contents entries (exam-service)
    - ``textbook_id`` — tasks linked to a textbook via textbook_tasks
    """
    params: dict = {"limit": limit, "offset": offset}

    if textbook_id:
        # Tasks via textbook_tasks join
        where = "tt.textbook_id = :tb_id AND tm.is_active = TRUE"
        params["tb_id"] = textbook_id
        from_clause = """
            tasks_master tm
            JOIN textbook_tasks tt ON tt.task_id = tm.id
        """
    elif toc_ids:
        where = "tm.toc_id = ANY(:toc_ids) AND tm.is_active = TRUE"
        params["toc_ids"] = toc_ids
        from_clause = "tasks_master tm LEFT JOIN knowledge_hierarchy kh ON kh.id = tm.skill_id"
    elif skill_ids:
        where = "tm.skill_id = ANY(:skill_ids) AND tm.is_active = TRUE"
        params["skill_ids"] = skill_ids
        from_clause = "tasks_master tm LEFT JOIN knowledge_hierarchy kh ON kh.id = tm.skill_id"
    elif skill_id:
        where = "tm.skill_id = :skill_id AND tm.is_active = TRUE"
        params["skill_id"] = skill_id
        from_clause = "tasks_master tm LEFT JOIN knowledge_hierarchy kh ON kh.id = tm.skill_id"
    else:
        raise HTTPException(status_code=400, detail="Provide skill_id, skill_ids, toc_ids, or textbook_id")

    if difficulty:
        where += " AND tm.difficulty = :difficulty"
        params["difficulty"] = difficulty
    if exclude_ids:
        where += " AND tm.id != ALL(:exclude_ids)"
        params["exclude_ids"] = exclude_ids

    order = "ORDER BY RANDOM()" if random_order else "ORDER BY tm.irt_difficulty"

    # For textbook queries, use a minimal column set (different shape)
    if textbook_id:
        q = f"""
            SELECT tm.id, tm.toc_id, tm.skill_id, tm.difficulty,
                   tm.question_text, tm.question_latex,
                   tm.answer_type, FALSE AS has_template
            FROM {from_clause}
            WHERE {where}
            {order}
            LIMIT :limit OFFSET :offset
        """
        rows = conn.execute(text(q), params).fetchall()
        return [
            {
                "task_id": r[0], "toc_id": r[1], "skill_id": r[2] or "",
                "difficulty": r[3] or "B", "question_text": _clean_text(r[4]),
                "question_latex": r[5], "answer_type": r[6] or "exact_number",
                "has_template": bool(r[7]),
            }
            for r in rows
        ]

    q = f"""
        SELECT {_TASK_COLS}
        FROM {from_clause}
        WHERE {where}
        {order}
        LIMIT :limit OFFSET :offset
    """
    rows = conn.execute(text(q), params).fetchall()
    return [_task_row_full(r) for r in rows]


class AvgDifficultyRequest(BaseModel):
    skill_ids: List[str]


@router.post("/tasks/avg-difficulty", summary="Average IRT b-param per skill")
def avg_difficulty(body: AvgDifficultyRequest, conn: Connection = Depends(get_db)):
    """Returns {skill_id: avg_irt_difficulty}.  Missing skills default to 0.0."""
    if not body.skill_ids:
        return {}
    rows = conn.execute(
        text("""
            SELECT skill_id, AVG(irt_difficulty)
            FROM tasks_master
            WHERE skill_id = ANY(:ids) AND is_active = TRUE
            GROUP BY skill_id
        """),
        {"ids": body.skill_ids},
    ).fetchall()
    result = {r[0]: float(r[1]) for r in rows}
    for sid in body.skill_ids:
        result.setdefault(sid, 0.0)
    return result


# ──────────────────────────────────────────────────────────────────────────────
# TOC  (textbook_toc)
# ──────────────────────────────────────────────────────────────────────────────

class ExpandTocRequest(BaseModel):
    toc_ids: List[int]


@router.post("/toc/expand", summary="Recursively expand TOC IDs to include children")
def expand_toc(body: ExpandTocRequest, conn: Connection = Depends(get_db)):
    """Returns the input ids plus all descendant toc ids."""
    if not body.toc_ids:
        return []
    rows = conn.execute(
        text("""
            WITH RECURSIVE children AS (
                SELECT id FROM textbook_toc WHERE id = ANY(:ids)
                UNION ALL
                SELECT t.id FROM textbook_toc t
                JOIN children c ON t.parent_id = c.id
            )
            SELECT DISTINCT id FROM children
        """),
        {"ids": body.toc_ids},
    ).fetchall()
    return [r[0] for r in rows]


# ──────────────────────────────────────────────────────────────────────────────
# Textbooks  (textbooks + textbook_toc + textbook_skill_map)
# ──────────────────────────────────────────────────────────────────────────────

@router.get("/textbooks", summary="List textbooks")
def list_textbooks(
    class_level: Optional[int] = None,
    conn: Connection = Depends(get_db),
):
    q = """
        SELECT textbook_id::text, title, authors, class_level,
               digitization_status, digitization_progress, tasks_extracted,
               cover_image_url
        FROM textbooks WHERE is_active = TRUE
    """
    params: dict = {}
    if class_level:
        q += " AND class_level = :cl"
        params["cl"] = class_level
    q += " ORDER BY class_level, title"
    rows = conn.execute(text(q), params).fetchall()
    return [
        {
            "textbook_id": r[0], "title": r[1], "authors": r[2] or [],
            "class_level": r[3],
            "digitization_status": r[4] or "pending",
            "digitization_progress": float(r[5] or 0),
            "tasks_extracted": r[6] or 0,
            "cover_image_url": r[7],
        }
        for r in rows
    ]


@router.get("/textbooks/{textbook_id}", summary="Get a single textbook")
def get_textbook(textbook_id: str, conn: Connection = Depends(get_db)):
    row = conn.execute(
        text("""
            SELECT textbook_id::text, title, subtitle, authors, class_level,
                   publisher, isbn, edition, country, language,
                   cover_image_url, total_pages,
                   digitization_status, digitization_progress, tasks_extracted,
                   is_active
            FROM textbooks WHERE textbook_id = :id AND is_active = TRUE
        """),
        {"id": textbook_id},
    ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail=f"Textbook {textbook_id!r} not found")
    return {
        "textbook_id": row[0], "title": row[1], "subtitle": row[2],
        "authors": row[3] or [], "class_level": row[4],
        "publisher": row[5], "isbn": row[6], "edition": row[7],
        "country": row[8] or "KZ", "language": row[9] or "ru",
        "cover_image_url": row[10], "total_pages": row[11],
        "digitization_status": row[12] or "pending",
        "digitization_progress": float(row[13] or 0),
        "tasks_extracted": row[14] or 0,
        "is_active": bool(row[15]),
    }


@router.get("/textbooks/{textbook_id}/toc", summary="Table of contents for a textbook")
def get_toc(textbook_id: str, conn: Connection = Depends(get_db)):
    rows = conn.execute(
        text("""
            SELECT id, textbook_id::text, level, number, title,
                   page_start, page_end, sort_order, parent_id
            FROM textbook_toc
            WHERE textbook_id = :tb_id
            ORDER BY sort_order
        """),
        {"tb_id": textbook_id},
    ).fetchall()
    return [
        {
            "id": r[0], "textbook_id": r[1], "level": r[2],
            "number": r[3], "title": r[4], "page_start": r[5],
            "page_end": r[6], "sort_order": r[7], "parent_id": r[8],
        }
        for r in rows
    ]


@router.get("/textbooks/{textbook_id}/coverage", summary="Digitization coverage per TOC entry")
def get_coverage(textbook_id: str, conn: Connection = Depends(get_db)):
    rows = conn.execute(
        text("""
            SELECT toc.id, toc.level, toc.number, toc.title,
                   COUNT(DISTINCT tsm.skill_id) AS skills_mapped,
                   COUNT(DISTINCT tm.id) AS tasks_available
            FROM textbook_toc toc
            LEFT JOIN textbook_skill_map tsm ON tsm.toc_id = toc.id
            LEFT JOIN tasks_master tm ON tm.toc_id = toc.id AND tm.is_active = TRUE
            WHERE toc.textbook_id = :tb_id
            GROUP BY toc.id, toc.level, toc.number, toc.title
            ORDER BY toc.sort_order
        """),
        {"tb_id": textbook_id},
    ).fetchall()
    return [
        {
            "toc_id": r[0], "level": r[1], "number": r[2],
            "title": r[3], "skills_mapped": r[4], "tasks_available": r[5],
        }
        for r in rows
    ]


@router.get("/toc/{toc_id}/skills", summary="Skills mapped to a TOC entry")
def get_toc_skills(toc_id: int, conn: Connection = Depends(get_db)):
    rows = conn.execute(
        text("""
            SELECT kh.id, kh.name_ru, tsm.role, tsm.confidence, tsm.is_main,
                   COUNT(tm.id) AS tasks_count
            FROM textbook_skill_map tsm
            JOIN knowledge_hierarchy kh ON kh.id = tsm.skill_id
            LEFT JOIN tasks_master tm
                ON tm.skill_id = tsm.skill_id AND tm.toc_id = tsm.toc_id AND tm.is_active = TRUE
            WHERE tsm.toc_id = :toc_id
            GROUP BY kh.id, kh.name_ru, tsm.role, tsm.confidence, tsm.is_main
            ORDER BY tsm.is_main DESC, tsm.role
        """),
        {"toc_id": toc_id},
    ).fetchall()
    return [
        {
            "skill_id": r[0], "skill_name": r[1], "role": r[2],
            "confidence": float(r[3]), "is_main": bool(r[4]),
            "tasks_count": r[5],
        }
        for r in rows
    ]
