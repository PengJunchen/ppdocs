#!/usr/bin/env bash
set -euo pipefail

echo "========================================"
echo "  Doc Parser API - Startup Script"
echo "========================================"
echo

if ! command -v uv &>/dev/null; then
    echo "[ERROR] uv not found. Install: https://docs.astral.sh/uv/getting-started/installation/"
    echo "  curl -LsSf https://astral.sh/uv/install.sh | sh"
    exit 1
fi

if [ ! -d ".venv" ]; then
    echo "[1/3] Creating virtual environment..."
    uv venv
else
    echo "[1/3] Virtual environment already exists"
fi

echo "[2/3] Installing dependencies..."
uv pip install -e ".[dev]"

echo "[3/3] Starting API server..."
echo
echo "  URL: http://localhost:8000"
echo "  Docs: http://localhost:8000/docs"
echo "  Postman: tests/postman/doc-parser-api.postman_collection.json"
echo

.venv/bin/python -m doc_parser.api.server --host 0.0.0.0 --port 8000
