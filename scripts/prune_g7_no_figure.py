#!/usr/bin/env python3
"""Backward-compatible wrapper — use prune_no_figure.py --class-level 7."""
from __future__ import annotations

import runpy
import sys
from pathlib import Path

if __name__ == "__main__":
    argv = list(sys.argv[1:])
    if "--class-level" not in argv:
        argv = ["--class-level", "7", *argv]
    sys.argv[1:] = argv
    raise SystemExit(runpy.run_path(str(Path(__file__).with_name("prune_no_figure.py")), run_name="__main__") or 0)
