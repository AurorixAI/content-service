#!/usr/bin/env python3
"""Copy OCR cache from running content-worker to host (survives rebuild).

Run while job is active — safe, read-only on worker:
    python scripts/backup_pipeline_cache.py
    docker exec content-worker python /app/scripts/backup_pipeline_cache.py --inside-container

After backup, cache lives in content-service/data/pipeline_cache/ on the host.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

CONTAINER = "content-worker"
CACHE_PATHS = (
    "/tmp/content_pipeline_cache",
    "/app/data/pipeline_cache",
)
HOST_DST = Path(__file__).resolve().parent.parent / "data" / "pipeline_cache"


def _sync_dir(src: Path, dst: Path) -> int:
    dst.mkdir(parents=True, exist_ok=True)
    copied = 0
    if not src.is_dir():
        return 0
    for f in src.glob("gemini_*.md"):
        target = dst / f.name
        if not target.exists() or f.stat().st_mtime > target.stat().st_mtime:
            shutil.copy2(f, target)
            copied += 1
    return copied


def backup_from_container() -> int:
    HOST_DST.mkdir(parents=True, exist_ok=True)
    total = 0
    for remote in CACHE_PATHS:
        cmd = ["docker", "cp", f"{CONTAINER}:{remote}/.", str(HOST_DST) + "/"]
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode == 0:
            n = len(list(HOST_DST.glob("gemini_*.md")))
            print(f"[OK] synced {remote} → {HOST_DST} ({n} files total)")
            total = n
            break
        if "No such container" in (r.stderr or ""):
            print(f"Container {CONTAINER} not found", file=sys.stderr)
            return 1
    if total == 0:
        print("[WARN] no cache files copied — is OCR running?", file=sys.stderr)
        return 1
    return 0


def backup_inside_container() -> int:
    """When already inside content-worker."""
    copied = 0
    for src in CACHE_PATHS:
        copied += _sync_dir(Path(src), HOST_DST)
    n = len(list(HOST_DST.glob("gemini_*.md")))
    print(f"[OK] {n} cache files in {HOST_DST} (+{copied} updated)")
    return 0 if n else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--inside-container", action="store_true")
    args = ap.parse_args()
    if args.inside_container:
        return backup_inside_container()
    return backup_from_container()


if __name__ == "__main__":
    sys.exit(main())
