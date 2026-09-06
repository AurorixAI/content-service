#!/usr/bin/env python3
"""Audit G5 figure storage, linkage quality, and prune candidates."""
from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, "/app")

from sqlalchemy import create_engine, text

from src.core.config import get_settings

# External figure required (prune if no attachment)
NEEDS_EXT_FIG = re.compile(
    r"по рисунку|на рисунке|рисунке\s+\d+|рис\.\s*\d+|рис\.\s*[а-яё]|"
    r"изображ[её]нн[а-я]+ на рис|пользуясь графиком[^,]*рисунке|"
    r"используя график[^.]*рис\.|изображенного на рисунке|"
    r"см\.\s*рис|на чертеже|по графику|смотри рис|"
    r"(?<![а-яё])черт[её]ж(?![а-яё])|"
    r"на\s+рис\.|рисунок\s+\d|график\s+функции",
    re.I,
)

# Table needs external visual if no inline data
NEEDS_TABLE = re.compile(
    r"таблиц|заполните\s+таблиц|по\s+таблиц|в\s+таблиц|составьте\s+таблиц",
    re.I,
)
INLINE_TABLE = re.compile(r"\|[^|]+\|", re.S)

# Draw offline — not solvable online anyway
DRAW_OFFLINE = re.compile(
    r"начерт[иь].*тетрад|нарисуй.*тетрад|построй.*тетрад|"
    r"измерь\s+линейк|вырежи|склей",
    re.I,
)

FIG_NUM_RE = re.compile(r"рис(?:унок|унке|\.)\s*(\d+)", re.I)

# compound_whole tasks that still need external visual but have none
EXTRA_PRUNE_IDS = frozenset({
    "G5_TB_3_85",      # table_fill_single
    "G5_TB_39_679",    # area_grid_single_answer
    "G5_TB_51_1228",   # figure_match_prose
})

USELESS_TYPES = frozenset({
    "photo", "portrait", "decorative", "cover", "ornament", "other",
})


def _fig_type(sem: dict | None) -> str:
    if not sem:
        return ""
    return str(sem.get("type") or sem.get("usefulness_reason") or "").lower()


def _is_useful(sem: dict | None) -> bool | None:
    if not sem:
        return None
    if "is_useful" in sem:
        return bool(sem["is_useful"])
    t = _fig_type(sem)
    if t in USELESS_TYPES:
        return False
    if t:
        return True
    return None


def _png_exists(fig: dict) -> bool:
    p = Path(get_settings().figures_dir) / fig["textbook_id"] / f"{fig['figure_id']}.png"
    return p.exists()


def find_prune_candidates(
    rows: list[dict],
    fig_by_id: dict[str, dict],
    *,
    include_compound_whole: bool = True,
) -> list[tuple[str, str, str]]:
    """Return (task_id, reason, preview)."""
    out: list[tuple[str, str, str]] = []
    seen: set[str] = set()

    def add(tid: str, reason: str, q: str) -> None:
        if tid not in seen:
            seen.add(tid)
            out.append((tid, reason, q[:90]))

    for r in rows:
        tid = r["id"]
        q = r["question_text"] or ""
        refs = list(r["linked_figs"] or [])
        refs = [f for f in refs if f]
        img = bool((r["image_url"] or "").strip()) or bool(refs)
        if DRAW_OFFLINE.search(q):
            continue

        fig_need = bool(NEEDS_EXT_FIG.search(q))
        tbl_need = bool(NEEDS_TABLE.search(q))
        inline_tbl = bool(INLINE_TABLE.search(q))

        # Broken/partial attachment when visual is required
        if refs:
            working = [f for f in refs if f in fig_by_id and _png_exists(fig_by_id[f])]
            missing = [f for f in refs if f not in fig_by_id or not _png_exists(fig_by_id[f])]
            if not working:
                add(tid, "broken_figure_link", q)
                continue
            if missing and (fig_need or tbl_need):
                add(tid, "partial_figure_link", q)
                continue

        if img:
            continue

        if tbl_need and inline_tbl and not fig_need:
            continue  # table data is in question text

        if not include_compound_whole and r.get("compound_whole"):
            continue

        if fig_need:
            add(tid, "no_figure", q)
        elif tbl_need and not inline_tbl:
            add(tid, "no_table_figure", q)
        elif tid in EXTRA_PRUNE_IDS:
            add(tid, "compound_whole_no_visual", q)
    return out


def audit_links(rows: list[dict], fig_by_id: dict[str, dict]) -> dict[str, list[tuple[str, str]]]:
    """Audit tasks that HAVE figure refs."""
    issues: dict[str, list[tuple[str, str]]] = defaultdict(list)

    for r in rows:
        tid = r["id"]
        q = r["question_text"] or ""
        refs: list[str] = list(r["linked_figs"] or [])
        if not refs:
            continue

        tb = r["textbook_id"]
        if not NEEDS_EXT_FIG.search(q) and not NEEDS_TABLE.search(q):
            issues["no_visual_hint"].append((tid, q[:80]))

        for fid in refs:
            fig = fig_by_id.get(fid)
            if not fig:
                issues["missing_figure_row"].append((tid, fid))
                continue
            if fig["textbook_id"] != tb:
                issues["wrong_textbook"].append((tid, fid))
            if not (fig["image_url"] or "").strip():
                issues["empty_image_url"].append((tid, fid))
            useful = _is_useful(fig.get("semantic_json"))
            if useful is False:
                issues["useless_figure"].append((tid, f"{fid} ({_fig_type(fig.get('semantic_json'))})"))
            elif useful is None and not (fig.get("alt_text") or "").strip():
                issues["undescribed_figure"].append((tid, fid))

        # Note: «рис.N» in textbook ≠ PDF page — heuristic disabled for linkage verdict
        pass

    # Tasks linked to figures whose PNG is missing
    for r in rows:
        tid = r["id"]
        for fid in list(r["linked_figs"] or []):
            fig = fig_by_id.get(fid)
            if not fig:
                continue
            p = Path(get_settings().figures_dir) / fig["textbook_id"] / f"{fid}.png"
            if not p.exists():
                issues["png_missing_on_disk"].append((tid, fid))

    return issues


def fetch_data(engine, class_level: int = 5) -> tuple[list[dict], dict[str, dict]]:
    with engine.connect() as c:
        rows = c.execute(
            text("""
                SELECT
                  tm.id,
                  tm.question_text,
                  COALESCE(tm.question_image_url, '') AS image_url,
                  tb.textbook_id::text AS textbook_id,
                  tb.title AS textbook,
                  COALESCE(
                    (SELECT COUNT(*) FROM task_figure_refs tfr WHERE tfr.task_id = tm.id),
                    0
                  ) AS fig_refs,
                  COALESCE(
                    (SELECT array_agg(tfr.figure_id ORDER BY tfr.order_idx)
                     FROM task_figure_refs tfr WHERE tfr.task_id = tm.id),
                    ARRAY[]::text[]
                  ) AS linked_figs,
                  tm.tags->>'compound_whole' AS compound_whole
                FROM tasks_master tm
                JOIN textbook_toc toc ON toc.id = tm.toc_id
                JOIN textbooks tb ON tb.textbook_id = toc.textbook_id
                WHERE tb.class_level = :level
                ORDER BY tm.id
            """),
            {"level": class_level},
        ).mappings().all()

        figs = c.execute(
            text("""
                SELECT tf.figure_id, tf.textbook_id::text AS textbook_id,
                       tf.page, tf.image_url, tf.alt_text, tf.semantic_json
                FROM task_figures tf
                JOIN textbooks tb ON tb.textbook_id = tf.textbook_id
                WHERE tb.class_level = :level
            """),
            {"level": class_level},
        ).mappings().all()

    fig_by_id = {f["figure_id"]: dict(f) for f in figs}
    return [dict(r) for r in rows], fig_by_id


def delete_tasks(engine, task_ids: list[str]) -> int:
    if not task_ids:
        return 0
    with engine.begin() as conn:
        conn.execute(
            text("DELETE FROM task_figure_refs WHERE task_id = ANY(:ids)"),
            {"ids": task_ids},
        )
        conn.execute(
            text("DELETE FROM textbook_tasks WHERE task_id = ANY(:ids)"),
            {"ids": task_ids},
        )
        n = conn.execute(
            text("DELETE FROM tasks_master WHERE id = ANY(:ids) RETURNING id"),
            {"ids": task_ids},
        ).rowcount
        # refresh textbook counts
        conn.execute(text("""
            UPDATE textbooks tb
            SET tasks_extracted = sub.cnt
            FROM (
              SELECT tt.textbook_id, COUNT(*) AS cnt
              FROM textbook_tasks tt
              JOIN textbooks t ON t.textbook_id = tt.textbook_id
              WHERE t.class_level = 5
              GROUP BY tt.textbook_id
            ) sub
            WHERE tb.textbook_id = sub.textbook_id AND tb.class_level = 5
        """))
    return n


def main() -> int:
    ap = argparse.ArgumentParser(description="G5 figure audit + prune")
    ap.add_argument("--prune", action="store_true", help="delete tasks without required visual")
    ap.add_argument("--execute", action="store_true")
    ap.add_argument("--include-compound-whole", action="store_true", default=True)
    args = ap.parse_args()

    engine = create_engine(get_settings().database_url)
    rows, fig_by_id = fetch_data(engine)

    # Storage summary
    with_img = sum(1 for r in rows if r["fig_refs"] > 0)
    useful_figs = sum(1 for f in fig_by_id.values() if _is_useful(f.get("semantic_json")) is True)
    useless_figs = sum(1 for f in fig_by_id.values() if _is_useful(f.get("semantic_json")) is False)
    undesc = sum(1 for f in fig_by_id.values() if _is_useful(f.get("semantic_json")) is None)

    print("=" * 64)
    print("G5 — хранение и привязка картинок")
    print("=" * 64)
    print(f"\nВсего задач: {len(rows)}")
    print(f"С task_figure_refs: {with_img}")
    print(f"\nФигур в task_figures: {len(fig_by_id)}")
    print(f"  is_useful=true: {useful_figs}")
    print(f"  is_useful=false: {useless_figs}")
    print(f"  без описания (semantic_json пуст): {undesc}")
    print("\nХранение:")
    print("  PNG: figures_dir/{textbook_uuid}/{figure_id}.png")
    print("  URL: /api/v1/figures/{textbook_uuid}/{figure_id}.png")
    print("  Описание: task_figures.semantic_json + alt_text (Gemini Vision)")
    print("  Связь: task_figure_refs (task_id, figure_id, order_idx)")

    sample_url = next(iter(fig_by_id.values()), {}).get("image_url", "")
    if sample_url:
        print(f"\nПример URL: {sample_url}")

    # PNG on disk
    settings = get_settings()
    png_ok = png_miss = 0
    missing_png_ids: list[str] = []
    for fid, fig in fig_by_id.items():
        p = Path(settings.figures_dir) / fig["textbook_id"] / f"{fid}.png"
        if p.exists():
            png_ok += 1
        else:
            png_miss += 1
            missing_png_ids.append(fid)
    print(f"\nPNG на диске ({settings.figures_dir}): {png_ok} ok, {png_miss} missing")
    if missing_png_ids:
        print(f"  missing: {missing_png_ids[:10]}")

    # Link audit
    issues = audit_links(rows, fig_by_id)
    print("\n--- Аудит привязок (задачи С картинкой) ---")
    for kind, items in sorted(issues.items(), key=lambda x: -len(x[1])):
        print(f"  {kind}: {len(items)}")
        for tid, detail in items[:5]:
            print(f"    {tid} | {detail}")
        if len(items) > 5:
            print(f"    ... +{len(items) - 5}")

    # Prune candidates
    prune = find_prune_candidates(rows, fig_by_id, include_compound_whole=args.include_compound_whole)
    by_reason: dict[str, int] = defaultdict(int)
    for _, reason, _ in prune:
        by_reason[reason] += 1

    print("\n--- Кандидаты на удаление (нет визуала, но нужен) ---")
    print(f"  Всего: {len(prune)}")
    for reason, cnt in sorted(by_reason.items()):
        print(f"    {reason}: {cnt}")

    compound = [p for p in prune if any(
        r["id"] == p[0] and r.get("compound_whole") for r in rows
    )]
    if compound:
        print(f"  из них compound_whole: {len(compound)}")

    for tid, reason, preview in prune[:12]:
        print(f"    {tid} [{reason}] | {preview}")
    if len(prune) > 12:
        print(f"    ... +{len(prune) - 12}")

    if args.prune:
        ids = [p[0] for p in prune]
        if not args.execute:
            print(f"\n[DRY RUN] удалит {len(ids)} задач. Добавь --execute")
            return 0
        n = delete_tasks(engine, ids)
        print(f"\nУдалено: {n} задач")
        with engine.connect() as c:
            left = c.execute(text("""
                SELECT COUNT(*) FROM tasks_master tm
                JOIN textbook_toc toc ON toc.id = tm.toc_id
                JOIN textbooks tb ON tb.textbook_id = toc.textbook_id
                WHERE tb.class_level = 5
            """)).scalar()
        print(f"G5 осталось: {left}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
