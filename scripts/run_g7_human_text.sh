#!/bin/sh
# G7 human_review reprocess — text/MCQ only, no coordinate loop, one attempt each
set -e
LOG=/tmp/g7_human_text.log
echo "=== G7 HUMAN TEXT VERIFY $(date -u) ===" | tee "$LOG"

python3 /app/scripts/run_smart_verify.py \
  --class-level 7 \
  --only-human-review \
  --reprocess \
  --skip-coordinate \
  --answer-authority ai_first \
  --loop \
  --limit 20 \
  --sleep 1 \
  2>&1 | tee -a "$LOG"

echo "=== DONE $(date -u) ===" | tee -a "$LOG"
