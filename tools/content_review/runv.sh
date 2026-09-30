#!/bin/bash
# usage: runv.sh <script.py> [args] — run a verifier in the SymPy image against the live DB
S=$(cd "$(dirname "$0")" && pwd)
docker run --rm --network algo-network -v $S:/audit -w /audit -e HOME=/tmp --entrypoint python algo-content-test:latex-self-review "$@" 2>&1 | grep -v -i "warn\|ErrorListener\|antlr\|^No character"
