#!/usr/bin/env python3
"""Build a read-only, reproducible safety queue for ``question_latex``.

The educational source (``question_text``) is never changed here.  This
utility only compares it with the UI projection (``question_latex``), checks
the renderer contract and KaTeX syntax, then writes two local JSON artifacts:

* the full queue of questions that are unsafe to make the sole UI projection;
* a small, representative dry-run batch for the DeepSeek backfill.

The script contains no INSERT/UPDATE/DELETE statements and makes no LLM
calls.  It requires the ``test`` Docker target because it keeps one Node/KaTeX
worker alive for the full audit instead of spawning Node once per task.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from collections import Counter, defaultdict
try:  # Python 3.11+
    from datetime import UTC, datetime
except ImportError:  # pragma: no cover - local audit compatibility on Python 3.9/3.10
    from datetime import datetime, timezone

    UTC = timezone.utc
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from sqlalchemy import create_engine, text


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
load_dotenv(ROOT / ".env")

from backfill_latex_deepseek import (  # noqa: E402
    NODE_BIN,
    _KATEX_MODULE,
    validate_display_contract,
    validate_professional_latex,
)


# Same parser contract as ``validate_with_katex`` in the backfill, but kept as
# one long-lived Node worker. This makes a full 35k-row audit practical and
# ensures the queue uses the exact validator that will gate a later write.
KATEX_WORKER_JS = "const katex = require(" + json.dumps(_KATEX_MODULE) + ");\n" + r"""
const readline = require('readline');

function validate(text) {
  try {
    const unescapedDollars = [...text.matchAll(/(?<!\\)\$/g)].length;
    if (unescapedDollars % 2 !== 0) throw new Error('unmatched_math_delimiter');

    const blockRe = /\$\$([^$]+)\$\$/g;
    let match;
    while ((match = blockRe.exec(text)) !== null) {
      const inner = match[1].trim();
      if (inner) katex.renderToString(inner, { throwOnError: true, strict: 'ignore', displayMode: true });
    }
    const withoutBlocks = text.replace(blockRe, '');
    const inlineRe = /\$([^$]+)\$/g;
    while ((match = inlineRe.exec(withoutBlocks)) !== null) {
      const inner = match[1].trim();
      if (inner) katex.renderToString(inner, { throwOnError: true, strict: 'ignore' });
    }
    return { ok: true, error: '' };
  } catch (error) {
    return { ok: false, error: String(error && (error.message || error)).slice(0, 300) };
  }
}

const reader = readline.createInterface({ input: process.stdin, crlfDelay: Infinity });
reader.on('line', (line) => {
  try {
    const payload = JSON.parse(line);
    process.stdout.write(JSON.stringify(validate(String(payload.text || ''))) + '\n');
  } catch (error) {
    process.stdout.write(JSON.stringify({ ok: false, error: 'worker_input_error: ' + String(error) }) + '\n');
  }
});
"""


class KaTeXWorker:
    """Sequential JSON-lines bridge to one isolated Node/KaTeX process."""

    def __enter__(self) -> "KaTeXWorker":
        self.process = subprocess.Popen(
            [NODE_BIN, "-e", KATEX_WORKER_JS],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            bufsize=1,
        )
        return self

    def validate(self, display: str) -> tuple[bool, str]:
        if not display or "$" not in display:
            return True, ""
        if self.process.poll() is not None:
            stderr = self.process.stderr.read().strip()[:300]
            return False, f"katex_worker_stopped: {stderr or 'unknown error'}"
        assert self.process.stdin is not None
        assert self.process.stdout is not None
        self.process.stdin.write(json.dumps({"text": display}, ensure_ascii=False) + "\n")
        self.process.stdin.flush()
        line = self.process.stdout.readline()
        if not line:
            stderr = self.process.stderr.read().strip()[:300]
            return False, f"katex_worker_no_response: {stderr or 'unknown error'}"
        try:
            result = json.loads(line)
        except json.JSONDecodeError as exc:
            return False, f"katex_worker_invalid_response: {exc}"
        return bool(result.get("ok")), str(result.get("error") or "")

    def __exit__(self, exc_type, exc, traceback) -> None:
        if self.process.stdin:
            self.process.stdin.close()
        self.process.terminate()
        try:
            self.process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            self.process.kill()
            self.process.wait(timeout=3)


def _risk_level(safety_reasons: list[str]) -> str:
    """Rank for review order, never as a claim that source data is wrong."""
    joined = " ".join(safety_reasons)
    if "invalid.katex" in joined or "semantic.question_latex.number" in joined:
        return "critical"
    if "semantic.question_latex.operator" in joined or "contract.question_latex" in joined:
        return "high"
    return "review"


def _primary_reason(record: dict[str, Any]) -> str:
    reasons = record["safety_reasons"]
    priorities = (
        "invalid.katex",
        "semantic.question_latex.number",
        "semantic.question_latex.operator",
        "contract.question_latex",
        "missing.question_latex",
        "semantic.question_latex.text",
    )
    for prefix in priorities:
        for reason in reasons:
            if reason.startswith(prefix):
                return reason
    return reasons[0]


def select_representative_batch(records: list[dict[str, Any]], size: int) -> list[dict[str, Any]]:
    """Choose a deterministic cross-section before any model-assisted repair."""
    risk_order = {"critical": 0, "high": 1, "review": 2}
    ordered = sorted(records, key=lambda row: (risk_order[row["risk"]], row["task_id"]))
    by_reason: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in ordered:
        by_reason[_primary_reason(record)].append(record)

    selected: list[dict[str, Any]] = []
    # First pass: one example of every failure mode. It catches prompt or gate
    # defects that a lexicographic first-25 sample would hide.
    for reason in sorted(by_reason):
        if len(selected) >= size:
            break
        selected.append(by_reason[reason].pop(0))
    # Second pass: fill by severity, deterministically.
    remaining = [row for rows in by_reason.values() for row in rows]
    remaining.sort(key=lambda row: (risk_order[row["risk"]], row["task_id"]))
    selected.extend(remaining[: max(0, size - len(selected))])

    batch: list[dict[str, Any]] = []
    for index, record in enumerate(selected, start=1):
        batch.append({
            **record,
            "batch_order": index,
            "selection_reason": f"representative:{_primary_reason(record)}",
        })
    return batch


def main() -> int:
    parser = argparse.ArgumentParser(description="Read-only question_latex safety queue export")
    parser.add_argument("--output", required=True, help="Full queue JSON output path")
    parser.add_argument("--batch-output", required=True, help="Representative dry-run batch JSON output path")
    parser.add_argument("--batch-size", type=int, default=25)
    args = parser.parse_args()
    if args.batch_size < 1:
        parser.error("--batch-size must be positive")

    db_url = os.environ.get("DATABASE_URL") or "postgresql://algo:algo_password@127.0.0.1:5434/algo_content"
    engine = create_engine(db_url)
    query = text("""
        SELECT id, question_text, question_latex, latex_status
        FROM tasks_master
        WHERE is_active = TRUE
          AND verification_status = 'verified'
        ORDER BY id
    """)

    total = 0
    safety_reason_counts: Counter[str] = Counter()
    style_reason_counts: Counter[str] = Counter()
    katex_reason_counts: Counter[str] = Counter()
    queue: list[dict[str, Any]] = []
    with engine.connect() as conn, KaTeXWorker() as katex:
        for task_id, question_text, question_latex, stored_status in conn.execute(query):
            total += 1
            source = str(question_text or "").strip()
            display = str(question_latex or "").strip()
            safety_reasons: list[str] = []
            style_reasons: list[str] = []

            if source and not display:
                safety_reasons.append("missing.question_latex")
            elif display:
                contract_ok, contract_reason = validate_display_contract("question", source, display)
                if not contract_ok:
                    safety_reasons.append(f"contract.question_latex.{contract_reason}")

                katex_ok, katex_error = katex.validate(display)
                if not katex_ok:
                    normalized_error = katex_error or "unknown"
                    safety_reasons.append(f"invalid.katex.{normalized_error}")
                    katex_reason_counts[normalized_error] += 1

                professional_ok, professional_reason = validate_professional_latex(display)
                if not professional_ok:
                    style_reasons.append(f"professional.question_latex.{professional_reason}")

            for reason in safety_reasons:
                safety_reason_counts[reason] += 1
            for reason in style_reasons:
                style_reason_counts[reason] += 1
            if not safety_reasons:
                continue

            fingerprint = hashlib.sha256(source.encode("utf-8")).hexdigest()
            record = {
                "task_id": str(task_id),
                "stored_latex_status": str(stored_status or "null"),
                "risk": _risk_level(safety_reasons),
                "safety_reasons": safety_reasons,
                "style_reasons": style_reasons,
                "canonical_fingerprint_sha256": fingerprint,
                "question_text": source,
                "question_latex": display,
            }
            queue.append(record)

    timestamp = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    report = {
        "mode": "read_only",
        "generated_at": timestamp,
        "selection": {
            "is_active": True,
            "verification_status": "verified",
            "safety_definition": "missing OR renderer-contract OR KaTeX OR semantic-preservation failure",
            "style_definition": "professional LaTeX house-style failure, reported separately",
        },
        "tasks_checked": total,
        "safety_queue_count": len(queue),
        "safety_reason_counts": dict(sorted(safety_reason_counts.items())),
        "professional_style_debt_on_safety_queue": dict(sorted(
            Counter(reason for item in queue for reason in item["style_reasons"]).items()
        )),
        "professional_style_debt_all_tasks": dict(sorted(style_reason_counts.items())),
        "katex_error_counts": dict(sorted(katex_reason_counts.items())),
        "records": queue,
    }
    batch = select_representative_batch(queue, args.batch_size)
    batch_report = {
        "mode": "read_only",
        "generated_at": timestamp,
        "source_queue_count": len(queue),
        "batch_size": len(batch),
        "write_safety": "This file is a dry-run selection only. No database values were changed.",
        "records": batch,
    }

    output = Path(args.output)
    batch_output = Path(args.batch_output)
    output.parent.mkdir(parents=True, exist_ok=True)
    batch_output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    batch_output.write_text(json.dumps(batch_report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print("READ-ONLY: no database rows were modified")
    print(f"Tasks checked: {total}")
    print(f"Safety queue: {len(queue)}")
    print(f"Representative batch: {len(batch)}")
    for reason, count in sorted(safety_reason_counts.items()):
        print(f"  {count:>6}  {reason}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
