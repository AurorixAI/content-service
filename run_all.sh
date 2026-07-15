#!/bin/bash
# run_all.sh - Runs paragraphs from 4 to 31 sequentially
LOG_DIR="/app/logs/batch_run"
mkdir -p "$LOG_DIR"

echo "=== STARTING BATCH DIGITIZATION (PARAGRAPHS 4 TO 31) ==="

for i in {4..31}; do
  echo "========================================"
  echo "  STARTING PARAGRAPH $i ($(date))"
  echo "========================================"
  
  python /app/run_paragraph.py "$i" 2>&1 | tee "$LOG_DIR/para_$i.log"
  
  STATUS=${PIPESTATUS[0]}
  if [ $STATUS -ne 0 ]; then
    echo "WARNING: Paragraph $i failed with exit code $STATUS! Moving to next."
  else
    echo "SUCCESS: Paragraph $i finished successfully."
  fi
  
  echo "Cooldown delay (10s)..."
  sleep 10
done

echo "=== BATCH DIGITIZATION COMPLETED! ==="
