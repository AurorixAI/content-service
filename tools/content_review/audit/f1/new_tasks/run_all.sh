#!/bin/bash
# re-run every skill's sympy verification (asserts) and regenerate the per-skill JSON
cd "$(dirname "$0")" && for f in gen_G*_S*.py; do python3 "$f" || exit 1; done
