#!/usr/bin/env bash

set -euo pipefail

PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cd "$PROJECT_ROOT"

echo "TestLab - SIMULATION MODE"
echo "结果目录: ${TESTLAB_RESULTS_DIR:-$PROJECT_ROOT/results}"

exec python -m streamlit run app.py \
    --server.address 127.0.0.1 \
    --server.port "${TESTLAB_PORT:-8501}"
