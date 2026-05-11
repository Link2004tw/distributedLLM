@echo off
REM Load Test Suite Runner

echo ============================================================
echo GPU Distributed System - Test Suite
echo ============================================================

set BASE_URL=http://127.0.0.1:8000
set CUDA_VISIBLE_DEVICES=0

echo.
echo [1/4] Checking services...
python -c "import httpx; r = httpx.get('%BASE_URL%/health', timeout=5); print('Load Balancer: OK')" 2>nul
if errorlevel 1 (
    echo Load Balancer: NOT RUNNING
    echo Start with: python -m uvicorn lb.load_balancer:app --port 8000
    exit /b 1
)

echo [2/4] Running Load Generator (100 requests, 10 concurrent)...
python client\load_generator.py --url %BASE_URL% --requests 100 --concurrency 10 --warmup 5

echo.
echo [3/4] Running Lag Tester (30s duration, 100ms interval)...
python client\lag_tester.py --url %BASE_URL% --duration 30 --interval 100

echo.
echo [4/4] Running Stress Test & Benchmark...
python client\stress_tester.py --url %BASE_URL% --mode both

echo.
echo ============================================================
echo Test run complete!
echo ============================================================
pause