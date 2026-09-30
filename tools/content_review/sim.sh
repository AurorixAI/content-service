#!/bin/bash
# usage: sim.sh <name> — build restore_J_<name>.json from fix_<name>.py and simulate diag/exam grading on the post-write state
S=$(cd "$(dirname "$0")" && pwd)
docker run --rm --network algo-network -v $S:/audit -e HOME=/tmp --entrypoint python algo-diagnostic-service:latest /audit/fix_build.py $1 >/dev/null || exit 1
docker run --rm --network algo-network -v $S:/audit -e HOME=/tmp --entrypoint python algo-diagnostic-service:latest /audit/spec_state_after.py /audit/restore_J_$1.json
docker run --rm -v /Users/arslan/Desktop/ALGO/diagnostic-service/src:/app/src:ro -v $S:/audit -w /app -e HOME=/tmp -e PYTHONPATH=/app --entrypoint python algo-diagnostic-service:latest /audit/grade_state.py diag 2>&1 | tail -3
docker run --rm -v /Users/arslan/Desktop/ALGO/exam-service/src:/app/src:ro -v $S:/audit -w /app -e HOME=/tmp -e PYTHONPATH=/app --entrypoint python algo-exam-service:latest /audit/grade_state.py exam 2>&1 | tail -3
