#!/bin/bash
# usage: split_run.sh <name> check            — build, validate, simulate diag/exam grading, KaTeX
#        split_run.sh <name> apply <approver>  — dry run, backup, execute
set -e
S=$(cd "$(dirname "$0")" && pwd); N=$1
P="docker run --rm --network algo-network -v $S:/audit -e HOME=/tmp --entrypoint python algo-diagnostic-service:latest"
if [ "$2" = check ]; then
  $P /audit/split_build.py $N
  docker run --rm -v /Users/arslan/Desktop/ALGO/diagnostic-service/src:/app/src:ro -v $S:/audit -w /app -e HOME=/tmp -e PYTHONPATH=/app --entrypoint python algo-diagnostic-service:latest /audit/grade_state.py diag 2>&1 | tail -3
  docker run --rm -v /Users/arslan/Desktop/ALGO/exam-service/src:/app/src:ro -v $S:/audit -w /app -e HOME=/tmp -e PYTHONPATH=/app --entrypoint python algo-exam-service:latest /audit/grade_state.py exam 2>&1 | tail -3
  node $S/katex_check.js $S/kx_split_$N.json 2>&1 | tail -3
elif [ "$2" = apply ]; then
  [ -n "$3" ] || { echo "approver required"; exit 1; }
  $P /audit/split_apply.py $N --approved-by $3 | tail -2 | grep -q "DRY RUN" || { echo "DRY RUN BLOCKED"; exit 1; }
  (cd /Users/arslan/Desktop/ALGO/algo-infrastructure/scripts && CONTENT_PG_CONTAINER=algo-content-db ./backup_algo_content.sh 2>&1 | grep "Backup OK")
  $P /audit/split_apply.py $N --approved-by $3 --execute | tail -2
fi
