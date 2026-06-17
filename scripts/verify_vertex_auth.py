#!/usr/bin/env python3
"""Verify Vertex AI ADC auth and project config.

Usage:
    docker exec content-worker python /app/scripts/verify_vertex_auth.py
    python scripts/verify_vertex_auth.py   # from content-service/ on host
"""
from __future__ import annotations

import sys

from pathlib import Path

sys.path.insert(0, "/app" if Path("/app/src").is_dir() else str(Path(__file__).resolve().parents[1]))

from src.core.config import get_settings
from src.pipeline.gemini_client import _get_adc_token, _vertex_project, call_gemini


def main() -> int:
    s = get_settings()
    print("VERTEX_PROJECT_ID:", s.vertex_project_id or "(not set)")
    print("VERTEX_LOCATION:", s.vertex_location)
    print("GOOGLE_APPLICATION_CREDENTIALS:", __import__("os").environ.get("GOOGLE_APPLICATION_CREDENTIALS", "(env not set)"))

    try:
        project = _vertex_project()
        token = _get_adc_token()
        print(f"ADC token: OK ({len(token)} chars)")
        print(f"Vertex project: {project}")
    except Exception as exc:
        print(f"ADC FAILED: {exc}")
        return 1

    try:
        reply = call_gemini("Reply with exactly: OK", max_tokens=16, json_mode=False)
        print(f"Vertex API test: {reply.strip()[:80]}")
    except Exception as exc:
        print(f"Vertex API FAILED: {exc}")
        return 1

    print("\nAll checks passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
