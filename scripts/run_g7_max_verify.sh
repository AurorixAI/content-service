#!/bin/sh
# G7 max-quality verify: split children → human_review full reprocess
set -e
LOG=/tmp/g7_max_verify.log
echo "=== G7 MAX VERIFY START $(date -u) ===" >> "$LOG"

echo "Phase 1: 11 split children (pending)" >> "$LOG"
python3 /app/scripts/run_smart_verify.py --class-level 7 --loop --limit 20 2>&1 | tee -a "$LOG"

echo "Phase 2: human_review full reprocess ($(date -u))" >> "$LOG"
python3 /app/scripts/run_smart_verify.py \
  --class-level 7 \
  --only-human-review \
  --reprocess \
  --loop \
  --limit 15 \
  --sleep 1 \
  2>&1 | tee -a "$LOG"

echo "=== G7 MAX VERIFY DONE $(date -u) ===" >> "$LOG"
