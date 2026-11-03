@echo off
title NEO Backend (http://localhost:8000)
cd /d "%~dp0backend"
echo Starting backend at http://localhost:8000  (API docs: http://localhost:8000/docs)
python -m uv run uvicorn app.main:app --reload --port 8000
pause
