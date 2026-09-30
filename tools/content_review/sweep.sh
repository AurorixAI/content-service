#!/bin/bash
S=$(cd "$(dirname "$0")" && pwd)
for f in eq_verify2 ineq_verify3 trig_verify ineq_trig arith_verify3 simp_verify; do
  echo "=== $f"
  docker run --rm --network algo-network -v $S:/audit -w /audit -e HOME=/tmp -e DATABASE_URL=postgresql://algo:algo_password@algo-content-db:5432/algo_content algo-content-test:latex-self-review python /audit/$f.py 2>&1 | grep -v "Warning\|ErrorListener\|^No character" | tail -4
done
