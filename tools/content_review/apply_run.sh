#!/bin/bash
# usage: apply_run.sh <spec-name> <batch-id>  — dry-run, then (if clean) backup and apply
set -e
S=$(cd "$(dirname "$0")" && pwd); C=/Users/arslan/Desktop/ALGO/content-service; N=$1; B=$2
R="docker run --rm --network algo-network -v $C/scripts:/app/scripts:ro -v $C/src:/app/src:ro -v $S:/audit -w /app -e HOME=/tmp -e PYTHONPATH=/app -e DATABASE_URL=postgresql://algo:algo_password@algo-content-db:5432/algo_content algo-content-test:latex-self-review python /audit/apply_restore.py --batch-id $B --spec /audit/restore_J_$N.json"
OUT=$($R --report /audit/restore_J_${N}_dry.json 2>&1 | grep -v "Warning\|ErrorListener\|^No character" || true)
echo "$OUT" | tail -12
echo "$OUT" | grep -q "DRY RUN" || { echo "DRY RUN BLOCKED"; exit 1; }
(cd /Users/arslan/Desktop/ALGO/algo-infrastructure/scripts && CONTENT_PG_CONTAINER=algo-content-db ./backup_algo_content.sh 2>&1 | grep "Backup OK")
$R --report /audit/restore_J_${N}_applied.json --execute 2>&1 | grep -v "Warning\|ErrorListener\|^No character" | tail -2
