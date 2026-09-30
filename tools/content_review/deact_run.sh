#!/bin/bash
# usage: deact_run.sh <batch-file> <batch-id> — dry-run, backup, execute
set -e
S=$(cd "$(dirname "$0")" && pwd); C=/Users/arslan/Desktop/ALGO/content-service
D="docker run --rm --network algo-network -v $C/scripts:/app/scripts:ro -v $S:/audit -w /app -e HOME=/tmp -e DATABASE_URL=postgresql://algo:algo_password@algo-content-db:5432/algo_content algo-content-test:latex-self-review python /audit/deactivate_batch_0923.py --batch-file /audit/$1 --batch-id $2 ${3:+--approved-by $3}"
$D 2>&1 | tail -2
(cd /Users/arslan/Desktop/ALGO/algo-infrastructure/scripts && CONTENT_PG_CONTAINER=algo-content-db ./backup_algo_content.sh 2>&1 | grep "Backup OK")
$D --execute 2>&1 | tail -2
