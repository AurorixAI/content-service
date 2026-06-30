#!/bin/sh
# Wait for any running smart_verify, then start G8 computable-only loop.
set -e
while python -c "
import subprocess
r = subprocess.run(
    ['pgrep', '-f', 'run_smart_verify.py'],
    capture_output=True,
)
raise SystemExit(0 if r.returncode == 0 else 1)
" 2>/dev/null; do
  echo "$(date +%H:%M:%S) waiting for previous smart_verify..."
  sleep 30
done
echo "$(date +%H:%M:%S) starting G8 sympy loop (--skip-text)"
exec python /app/scripts/run_smart_verify.py --class-level 8 --skip-text --loop --sleep 1
