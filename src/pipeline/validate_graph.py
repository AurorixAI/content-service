"""
Validate Graph — Quality Report (L3 graph)
===========================================
1. Программные проверки: циклы, покрытие, изолированные подтемы
2. Gemini-ревью: эксперт проверяет весь граф как единое целое
3. Итоговый отчёт в JSON

Запуск:
  python3 -m src.pipeline.validate_graph \
    --prereq data/curriculum/prerequisites_class7.json \
    --importance data/curriculum/importance_class7.json \
    --out data/curriculum/quality_report_class7.json
"""
from __future__ import annotations

import argparse
import json
import logging
from collections import defaultdict, deque

from src.pipeline.gemini_client import call_gemini, get_pro_model, parse_json_response

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")


# ── 1. Программные проверки ────────────────────────────────────────────────────

def _detect_cycles(edges: list[dict]) -> list[list[str]]:
    """Ищет циклы через DFS. Возвращает список найденных циклов."""
    graph = defaultdict(list)
    for e in edges:
        graph[e["skill_id"]].append(e["prerequisite_id"])

    visited = set()
    rec_stack = set()
    cycles = []

    def dfs(node, path):
        visited.add(node)
        rec_stack.add(node)
        for neighbor in graph[node]:
            if neighbor not in visited:
                dfs(neighbor, path + [neighbor])
            elif neighbor in rec_stack:
                cycle_start = path.index(neighbor) if neighbor in path else -1
                if cycle_start >= 0:
                    cycles.append(path[cycle_start:] + [neighbor])

    for node in list(graph.keys()):
        if node not in visited:
            dfs(node, [node])

    return cycles


def _programmatic_checks(prereq_data: dict, importance_data: dict) -> dict:
    all_edges = prereq_data.get("edges", [])

    # All L3 subtopics from importance (skip L2 cluster IDs)
    all_subtopics = set()
    for cluster in importance_data.get("data", []):
        for item in cluster.get("subtopics", []):
            all_subtopics.add(item["node_id"])    # L3 only

    # Subtopics participating in edges (current grade only)
    class_level = prereq_data.get("class_level", 0)
    grade_prefix = f"G{class_level}_"
    current_subtopics = {s for s in all_subtopics if s.startswith(grade_prefix)}

    subtopics_with_deps = set()
    for e in all_edges:
        sid = e["skill_id"]
        pid = e["prerequisite_id"]
        subtopics_with_deps.add(sid)
        if pid.startswith(grade_prefix):
            subtopics_with_deps.add(pid)

    # Isolated = current grade subtopics not in any edge
    isolated = current_subtopics - subtopics_with_deps

    cycles = _detect_cycles(all_edges)

    hard_count = sum(1 for e in all_edges if e.get("dependency_type") == "hard")
    soft_count = sum(1 for e in all_edges if e.get("dependency_type") == "soft")
    cross_grade = sum(1 for e in all_edges if e.get("is_cross_grade"))

    avg_weight = round(sum(e.get("weight", 0) for e in all_edges) / len(all_edges), 2) if all_edges else 0
    avg_criticality = round(sum(e.get("criticality", 0) for e in all_edges) / len(all_edges), 2) if all_edges else 0

    return {
        "total_subtopics": len(current_subtopics),
        "total_edges": len(all_edges),
        "hard_edges": hard_count,
        "soft_edges": soft_count,
        "cross_grade_edges": cross_grade,
        "coverage_pct": round(len(subtopics_with_deps) / len(current_subtopics) * 100, 1) if current_subtopics else 0,
        "isolated_subtopics": sorted(isolated),
        "isolated_count": len(isolated),
        "cycles_found": len(cycles),
        "cycles": cycles,
        "avg_weight": avg_weight,
        "avg_criticality": avg_criticality,
        "status": "OK" if not cycles else "ERRORS",
    }


# ── 2. Gemini-ревью ────────────────────────────────────────────────────────────

def _build_review_prompt(class_level: int, edges: list[dict], subtopics_info: list[dict]) -> str:
    edges_text = json.dumps(edges, ensure_ascii=False, indent=2)
    subtopics_text = json.dumps(subtopics_info, ensure_ascii=False, indent=2)
    return f"""Ты — старший методист математического образования (PhD, 15+ лет практики).
Проведи экспертную проверку L3→L3 графа зависимостей для {class_level} класса.

ПОДТЕМЫ L3 (класс {class_level}):
{subtopics_text}

ВСЕ РЁБРА ЗАВИСИМОСТЕЙ:
{edges_text}

ЗАДАЧА — ЭКСПЕРТНАЯ ОЦЕНКА:
Оцени качество всего графа L3→L3 зависимостей целиком.

Проверь:
1. Математическую корректность каждого ребра — действительно ли B нужен для A?
2. Полноту — нет ли важных пропущенных зависимостей между подтемами?
3. Избыточность — есть ли лишние транзитивные рёбра?
4. Правильность типов (hard/soft) — не перепутаны ли они?
5. Адекватность weight и criticality
6. Cross-grade рёбра — имеют ли смысл зависимости с предыдущим классом?

ФОРМАТ ОТВЕТА (строгий JSON):
{{
  "overall_score": 8,
  "verdict": "GOOD",
  "strengths": ["..."],
  "issues": [
    {{
      "type": "WRONG_TYPE|MISSING_EDGE|REDUNDANT|BAD_WEIGHT|CYCLE_RISK|OTHER",
      "edge": "skill_id → prerequisite_id",
      "description": "...",
      "severity": "HIGH|MEDIUM|LOW"
    }}
  ],
  "missing_edges": [
    {{
      "skill_id": "G{class_level}_P##",
      "prerequisite_id": "G{class_level}_P## или G{class_level-1}_P##",
      "dependency_type": "hard",
      "reason": "Почему эта зависимость важна"
    }}
  ],
  "summary": "Один абзац — итоговая оценка графа"
}}

overall_score: 1-10 (10 = идеально)
verdict: "EXCELLENT" (9-10) | "GOOD" (7-8) | "ACCEPTABLE" (5-6) | "NEEDS_REWORK" (<5)
"""


def _gemini_review(prereq_data: dict, importance_data: dict) -> dict:
    edges = prereq_data.get("edges", [])
    class_level = prereq_data.get("class_level", 0)

    if not edges:
        log.warning("No edges to review")
        return {"error": "no edges", "overall_score": 0}

    # Build subtopic info list for context
    subtopics_info = []
    for cluster in importance_data.get("data", []):
        for s in cluster.get("subtopics", []):
            subtopics_info.append({
                "id": s["node_id"],
                "name": s.get("name", ""),
                "cluster": cluster["cluster_id"],
            })

    log.info("Reviewing %d edges for class %d ...", len(edges), class_level)

    try:
        raw = call_gemini(
            _build_review_prompt(class_level, edges, subtopics_info),
            model=get_pro_model(),
            temperature=0.2,
            max_tokens=16384,
            json_mode=True,
            timeout=240,
            thinking_budget=2048,
        )
        review = parse_json_response(raw)
        score = review.get("overall_score", 0)
        verdict = review.get("verdict", "?")
        issues = review.get("issues", [])
        missing = review.get("missing_edges", [])
        log.info("  → score=%d verdict=%s issues=%d missing=%d", score, verdict, len(issues), len(missing))
        return review
    except Exception as exc:
        log.error("  FAILED: %s", exc)
        return {"error": str(exc), "overall_score": 0}


# ── 3. Итоговый отчёт ─────────────────────────────────────────────────────────

def _build_report(checks: dict, review: dict) -> dict:
    score = review.get("overall_score", 0)
    issues = review.get("issues", [])
    missing = review.get("missing_edges", [])
    high_issues = [i for i in issues if i.get("severity") == "HIGH"]

    return {
        "programmatic_checks": checks,
        "gemini_review": {
            "overall_score": score,
            "verdict": review.get("verdict", "?"),
            "total_issues": len(issues),
            "high_severity_issues": len(high_issues),
            "total_missing_edges": len(missing),
            "summary": review.get("summary", ""),
        },
        "issues": issues,
        "missing_edges": missing,
        "strengths": review.get("strengths", []),
        "overall_verdict": (
            "PRODUCTION_READY" if score >= 8 and not checks["cycles"] and not high_issues
            else "NEEDS_REVIEW" if score >= 6
            else "NEEDS_REWORK"
        ),
    }


# ── Main ──────────────────────────────────────────────────────────────────────

def run(prereq_path: str, importance_path: str, out_path: str) -> None:
    log.info("Loading files ...")
    with open(prereq_path, encoding="utf-8") as f:
        prereq_data = json.load(f)
    with open(importance_path, encoding="utf-8") as f:
        importance_data = json.load(f)

    log.info("=== Step 1: Programmatic checks ===")
    checks = _programmatic_checks(prereq_data, importance_data)
    log.info("Total edges: %d | Coverage: %s%% | Cycles: %d | Isolated: %d | Status: %s",
             checks["total_edges"], checks["coverage_pct"],
             checks["cycles_found"], checks["isolated_count"], checks["status"])

    if checks["cycles"]:
        log.error("CYCLES FOUND: %s", checks["cycles"])
    if checks["isolated_subtopics"]:
        log.warning("ISOLATED (no deps): %s", checks["isolated_subtopics"])

    log.info("=== Step 2: Gemini expert review ===")
    review = _gemini_review(prereq_data, importance_data)

    log.info("=== Step 3: Building report ===")
    report = _build_report(checks, review)

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    log.info("━" * 60)
    log.info("OVERALL VERDICT: %s", report["overall_verdict"])
    log.info("Gemini score: %s/10 | Verdict: %s",
             report["gemini_review"]["overall_score"],
             report["gemini_review"]["verdict"])
    log.info("Issues (HIGH): %d | Missing edges: %d",
             report["gemini_review"]["high_severity_issues"],
             report["gemini_review"]["total_missing_edges"])
    log.info("Report saved: %s", out_path)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--prereq", required=True)
    parser.add_argument("--importance", required=True)
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    run(args.prereq, args.importance, args.out)
