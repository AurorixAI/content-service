#!/bin/bash
# usage: bank_check.sh — exact_bank_check against live DB with current diagnostic-service source (expect {})
cd "$(dirname "$0")" && docker run --rm --network algo-network -v $PWD:/audit -v /Users/arslan/Desktop/ALGO/diagnostic-service/src:/app/src:ro -w /app -e PYTHONPATH=/app -e HOME=/tmp --entrypoint python algo-diagnostic-service:latest /audit/exact_bank_check.py
