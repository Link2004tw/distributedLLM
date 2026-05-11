@echo off
REM GPU Worker - Test Runner
REM Run tests from project root

echo ============================================================
echo GPU Worker Test Suite
echo ============================================================

REM Set environment
set TEST_WORKER_URL=http://127.0.0.1:8001
set TEST_LB_URL=http://127.0.0.1:8000
set CUDA_VISIBLE_DEVICES=0

REM Check if services are running
echo.
echo [1/4] Checking services...
python -c "import httpx; r = httpx.get('http://127.0.0.1:8001/health', timeout=5); print('Worker: OK')" 2>nul
if errorlevel 1 echo Worker: NOT RUNNING - start with: python -m uvicorn workers.gpu_worker:app --port 8001

python -c "import httpx; r = httpx.get('http://127.0.0.1:8000/health', timeout=5); print('Load Balancer: OK')" 2>nul
if errorlevel 1 echo Load Balancer: NOT RUNNING - start with: python -m uvicorn lb.load_balancer:app --port 8000

REM Quick smoke test
echo.
echo [2/4] Running quick smoke test...
python tests/test_gpu_worker.py

REM Run pytest
echo.
echo [3/4] Running pytest...
python -m pytest tests/ -v --tb=short

REM Ollama health check
echo.
echo [4/4] Running Ollama health check...
python tests/test_ollama.py

echo.
echo ============================================================
echo Test run complete!
echo ============================================================
pause