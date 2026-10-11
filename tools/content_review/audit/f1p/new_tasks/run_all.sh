#!/bin/bash
# re-run every skill's sympy verification (asserts) and regenerate per-skill JSON (ids avoid /tmp/gen_ids.txt snapshot of GEN_* ids)
cd "$(dirname "$0")" && for f in gen_G1*.py; do python3 "$f" || exit 1; done
