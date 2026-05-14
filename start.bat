@echo off
setlocal

echo ========================================
echo   Doc Parser API - Startup Script
echo ========================================
echo.

where uv >nul 2>nul
if %errorlevel% neq 0 (
    echo [ERROR] uv not found. Install: https://docs.astral.sh/uv/getting-started/installation/
    echo   Windows: powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
    exit /b 1
)

if not exist ".venv" (
    echo [1/3] Creating virtual environment...
    uv venv
) else (
    echo [1/3] Virtual environment already exists
)

echo [2/3] Installing dependencies...
uv pip install -e ".[dev]"

echo [3/3] Starting API server...
echo.
echo   URL: http://localhost:8000
echo   Docs: http://localhost:8000/docs
echo   Postman: tests/postman/doc-parser-api.postman_collection.json
echo.

.venv\Scripts\python.exe -m doc_parser.api.server --host 0.0.0.0 --port 8000
