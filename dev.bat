@echo off
set PYTHONPATH=src
echo Starting Sentinel Backend on http://localhost:8000...
.\.venv\Scripts\python.exe -m uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
