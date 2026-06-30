#!/usr/bin/env python3
"""Backward-compatible wrapper — use backfill_latex.py --class-level 8."""
from __future__ import annotations

import runpy
import sys
from pathlib import Path

sys.argv = [sys.argv[0], "--class-level", "8", *sys.argv[1:]]
raise SystemExit(runpy.run_path(str(Path(__file__).with_name("backfill_latex.py")), run_name="__main__") or 0)
