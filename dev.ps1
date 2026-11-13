$env:PYTHONPATH = "src"
Write-Host "Starting Sentinel Backend on http://localhost:8000..." -ForegroundColor Cyan
& ".\.venv\Scripts\python.exe" -m uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
