echo "========================================="
echo "Starting Distributed LLM System (All Nodes)"
echo "========================================="

echo "1. Starting Master Node (Port 9000)..."
Start-Process powershell -ArgumentList "-NoExit", "-Command", "python -m uvicorn master.monitor:app --host 127.0.0.1 --port 9000"

echo "2. Starting Worker 1 (Port 8001)..."
Start-Process powershell -ArgumentList "-NoExit", "-Command", "`$env:WORKER_ID='worker-1'; `$env:WORKER_PORT='8001'; python -m uvicorn workers.worker:app --host 127.0.0.1 --port 8001"

echo "3. Starting Worker 2 (Port 8002)..."
Start-Process powershell -ArgumentList "-NoExit", "-Command", "`$env:WORKER_ID='worker-2'; `$env:WORKER_PORT='8002'; python -m uvicorn workers.worker:app --host 127.0.0.1 --port 8002"

echo "4. Starting Worker 3 (Port 8003)..."
Start-Process powershell -ArgumentList "-NoExit", "-Command", "`$env:WORKER_ID='worker-3'; `$env:WORKER_PORT='8003'; python -m uvicorn workers.worker:app --host 127.0.0.1 --port 8003"

echo "5. Starting Worker 4 (Port 8004)..."
Start-Process powershell -ArgumentList "-NoExit", "-Command", "`$env:WORKER_ID='worker-4'; `$env:WORKER_PORT='8004'; python -m uvicorn workers.worker:app --host 127.0.0.1 --port 8004"

echo "6. Starting Load Balancer (Port 8000)..."
Start-Process powershell -ArgumentList "-NoExit", "-Command", "python -m uvicorn lb.load_balancer:app --host 127.0.0.1 --port 8000"

echo "7. Starting Dashboard (Port 7000)..."
Start-Process powershell -ArgumentList "-NoExit", "-Command", "python -m uvicorn dashboard.app:app --host 127.0.0.1 --port 7000"

echo ""
echo "Waiting 15 seconds for all services to boot up..."
Start-Sleep -Seconds 15

echo "========================================="
echo "Running Initial Load Test (10 requests, 2 concurrent)"
echo "========================================="
python client/load_generator.py --requests 10 --concurrency 2

echo ""
echo "========================================="
echo "Services are now running!"
echo "To execute the larger tests, run these manually:"
echo "python client/load_generator.py --requests 100 --concurrency 20"
echo "python client/load_generator.py --requests 500 --concurrency 50"
echo "python client/load_generator.py --requests 1000 --concurrency 50"
echo "========================================="
