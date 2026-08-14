#!/usr/bin/env python3
"""Rebuild diagnostic report error entries from the authoritative answer/task IDs.

Old reports may have been hydrated by skill ID or question-text similarity. Both
are ambiguous. This script reads diag_answers.task_id, then copies the matching
task's canonical values and display-LaTeX fields. It is dry-run by default.
"""
from __future__ import annotations

import argparse
import json

import psycopg2


def _task_rows(cursor):
    cursor.execute(
        """
        SELECT id, question_text, question_latex, correct_answer,
               correct_answer_latex, answer_type, distractor_meta, answer_options
        FROM tasks_master
        """
    )
    return {
        row[0]: {
            "question_text": row[1], "question_latex": row[2],
            "correct_answer": row[3], "correct_answer_latex": row[4],
            "answer_type": row[5], "distractor_meta": row[6] or [],
            "answer_options": row[7] or [],
        }
        for row in cursor.fetchall()
    }


def _option_value(option):
    if isinstance(option, dict):
        return str(option.get("value") or option.get("text") or option.get("content") or "").strip()
    return str(option or "").strip()


def _option_latex(option):
    if isinstance(option, dict):
        return str(option.get("value_latex") or option.get("latex") or option.get("content_latex") or "").strip()
    return ""


def _build_pattern(answer, task, skill_names):
    task_id, student_answer, category, skill_id, outcome = answer
    correct = task["correct_answer"] or ""
    canonical_options = [_option_value(option) for option in task["answer_options"]]
    canonical_options = [option for option in canonical_options if option]
    if not canonical_options:
        canonical_options = [correct] if correct else []
        canonical_options.extend(
            str(item.get("value") or "").strip()
            for item in task["distractor_meta"] if isinstance(item, dict)
        )
    canonical_options = list(dict.fromkeys(option for option in canonical_options if option))

    display_options = []
    for option in canonical_options:
        if option == correct:
            display_options.append(task["correct_answer_latex"] or option)
            continue
        display_options.append(next(
            (str(item.get("value_latex") or item.get("value") or option)
             for item in task["distractor_meta"]
             if isinstance(item, dict) and str(item.get("value") or "") == option),
            option,
        ))

    explanation = None
    for item in task["distractor_meta"]:
        if isinstance(item, dict) and str(item.get("value") or "").strip() == str(student_answer or "").strip():
            explanation = item.get("explanation_latex") or item.get("explanation") or item.get("error_logic")
            break

    return {
        "task_id": task_id,
        "skill_id": skill_id,
        "skill_name_ru": skill_names.get(skill_id, skill_id),
        "question_text": task["question_text"],
        "question_latex": task["question_latex"],
        "answer_type": task["answer_type"] or "text",
        "answer_options": canonical_options,
        "answer_options_latex": display_options,
        "eval_category": category,
        "student_answer": student_answer if student_answer not in ("", "wrong", "x_wrong_x") else None,
        "correct_answer": correct or None,
        "correct_answer_latex": task["correct_answer_latex"] or correct or None,
        "distractor_explanation": explanation,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--execute", action="store_true", help="write rebuilt report_json to algo_diagnostic")
    args = parser.parse_args()

    content = psycopg2.connect(dbname="algo_content", user="algo", password="algo_password", host="127.0.0.1", port=5434)
    diagnostic = psycopg2.connect(dbname="algo_diagnostic", user="algo", password="algo_password", host="127.0.0.1", port=5433)
    content_cursor, diagnostic_cursor = content.cursor(), diagnostic.cursor()
    tasks = _task_rows(content_cursor)
    diagnostic_cursor.execute("SELECT id, session_id, report_json FROM diag_reports WHERE report_json IS NOT NULL")
    reports = diagnostic_cursor.fetchall()

    changed = 0
    for report_id, session_id, report_json in reports:
        payload = json.loads(report_json) if isinstance(report_json, str) else report_json
        old_patterns = payload.get("error_patterns") or []
        skill_names = {pattern.get("skill_id"): pattern.get("skill_name_ru") for pattern in old_patterns if pattern.get("skill_id")}
        diagnostic_cursor.execute(
            "SELECT task_id, student_answer, eval_category, skill_id, outcome FROM diag_answers WHERE session_id = %s ORDER BY answered_at, id",
            (session_id,),
        )
        wrong_answers = [answer for answer in diagnostic_cursor.fetchall() if float(answer[4] or 0) < 1.0]
        rebuilt = [_build_pattern(answer, tasks[answer[0]], skill_names) for answer in wrong_answers if answer[0] in tasks][:12]
        payload["error_patterns"] = rebuilt
        payload.setdefault("report_meta", {})["error_patterns_version"] = 2
        changed += 1
        if args.execute:
            diagnostic_cursor.execute(
                "UPDATE diag_reports SET report_json = %s::jsonb WHERE id = %s",
                (json.dumps(payload, ensure_ascii=False), report_id),
            )

    if args.execute:
        diagnostic.commit()
    print(f"{'Rebuilt' if args.execute else 'Would rebuild'} {changed} diagnostic reports from exact diag_answers.task_id records.")


if __name__ == "__main__":
    main()
