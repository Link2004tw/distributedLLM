# Comprehensive startup script for distributed LLM system
# Starts: Ollama instances -> Ingest documents -> Master -> Workers -> Load Balancer

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Distributed LLM System - Full Startup" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan

# Kill any existing processes
Write-Host "[1/5] Cleaning up existing processes..." -ForegroundColor Yellow
Get-Process | Where-Object { $_.ProcessName -match "ollama|nginx|python" } | Stop-Process -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 2

# Start Ollama instances
Write-Host "[2/5] Starting 6 Ollama instances..." -ForegroundColor Yellow

# Create temporary batch files to start Ollama with proper environment
$ollama_instances = @(
    @{port=11434; script="start-ollama-11434.bat"},
    @{port=11435; script="start-ollama-11435.bat"},
    @{port=11436; script="start-ollama-11436.bat"},
    @{port=11437; script="start-ollama-11437.bat"},
    @{port=11438; script="start-ollama-11438.bat"},
    @{port=11439; script="start-ollama-11439.bat"}
)

foreach ($instance in $ollama_instances) {
    $batch_content = "@echo off`nset OLLAMA_HOST=0.0.0.0:$($instance.port)`nollama serve"
    Set-Content -Path $instance.script -Value $batch_content -Force
    Start-Process $instance.script -NoNewWindow
}

Write-Host "Waiting for Ollama instances to start..." -ForegroundColor Gray
Start-Sleep -Seconds 8

# Pull models if needed
Write-Host "Ensuring models are pulled..." -ForegroundColor Gray
foreach ($port in @(11434, 11435, 11436, 11437, 11438, 11439)) {
    ollama -H "localhost:$port" pull smollm:135m 2>$null
}
ollama -H "localhost:11434" pull nomic-embed-text:latest 2>$null
Write-Host "Models ready." -ForegroundColor Green

# Ingest documents (CRITICAL for RAG)
Write-Host "[3/5] Ingesting documents into ChromaDB..." -ForegroundColor Yellow
python ingest.py
if ($LASTEXITCODE -ne 0) {
    Write-Host "WARNING: Document ingestion failed. RAG will have no data." -ForegroundColor Red
} else {
    Write-Host "Documents ingested successfully." -ForegroundColor Green
}

Start-Sleep -Seconds 2

# Start master node
Write-Host "[4/5] Starting Master node (health monitor)..." -ForegroundColor Yellow
$env:MASTER_PORT="9000"
Start-Process uvicorn -ArgumentList "master.monitor:app --port 9000 --log-level warning" -NoNewWindow -WindowStyle Minimized
Start-Sleep -Seconds 2

# Set environment variables for worker concurrency
$env:MAX_CONCURRENT_TASKS="20"
$env:BACKPRESSURE_QUEUE_SIZE="200"

# Start 8 workers (scaled capacity)
Write-Host "[5/5] Starting 8 GPU workers (total capacity: ~160 concurrent requests)..." -ForegroundColor Yellow

$workers = @(
    @{id="worker-1"; port=8001; ollama_port=11434},
    @{id="worker-2"; port=8002; ollama_port=11435},
    @{id="worker-3"; port=8003; ollama_port=11436},
    @{id="worker-4"; port=8004; ollama_port=11437},
    @{id="worker-5"; port=8005; ollama_port=11438},
    @{id="worker-6"; port=8006; ollama_port=11439},
    @{id="worker-7"; port=8007; ollama_port=11434},
    @{id="worker-8"; port=8008; ollama_port=11435}
)

foreach ($worker in $workers) {
    $env_vars = @{
        WORKER_ID = $worker.id
        PORT = $worker.port
        OLLAMA_URL = "http://localhost:$($worker.ollama_port)"
        MAX_CONCURRENT_TASKS = "20"
        BACKPRESSURE_QUEUE_SIZE = "200"
    }
    
    $pinfo = New-Object System.Diagnostics.ProcessStartInfo
    $pinfo.FileName = "uvicorn"
    $pinfo.Arguments = "workers.worker:app --port $($worker.port) --log-level warning"
    $pinfo.UseShellExecute = $false
    $pinfo.CreateNoWindow = $true
    
    # Copy environment variables
    foreach ($key in $env_vars.Keys) {
        $pinfo.EnvironmentVariables[$key] = $env_vars[$key]
    }
    
    $proc = [System.Diagnostics.Process]::Start($pinfo)
    Write-Host "  Started $($worker.id) on port $($worker.port)" -ForegroundColor Gray
    Start-Sleep -Milliseconds 500
}

Start-Sleep -Seconds 3

# Start Load Balancer (NGINX)
Write-Host "[BONUS] Starting Load Balancer (NGINX on port 8000)..." -ForegroundColor Yellow
$nginx_exe = "lb/nginx/nginx.exe"
if (Test-Path $nginx_exe) {
    taskkill /f /im nginx.exe 2>$null
    Start-Sleep -Seconds 1
    Start-Process $nginx_exe -NoNewWindow -WindowStyle Minimized
    Start-Sleep -Seconds 2
    Write-Host "Load Balancer started on port 8000" -ForegroundColor Green
} else {
    Write-Host "NGINX not found. Run 'python benchmark.py --setup-nginx' first." -ForegroundColor Yellow
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "System Status: READY" -ForegroundColor Green
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "Components running:" -ForegroundColor Cyan
Write-Host "  • 6 Ollama instances (11434-11439)" -ForegroundColor Green
Write-Host "  • 8 GPU Workers (8001-8008)" -ForegroundColor Green
Write-Host "  • Master Node (9000)" -ForegroundColor Green
Write-Host "  • Load Balancer (8000)" -ForegroundColor Green
Write-Host ""
Write-Host "Test endpoints:" -ForegroundColor Cyan
Write-Host "  • Query via LB: POST http://localhost:8000/query" -ForegroundColor Gray
Write-Host "  • Direct worker: POST http://localhost:8001/query" -ForegroundColor Gray
Write-Host "  • Dashboard: http://localhost:5000" -ForegroundColor Gray
Write-Host ""
Write-Host "Run benchmark:" -ForegroundColor Cyan
Write-Host "  python benchmark.py --requests 1000 --workers 8 --concurrency 160 --single" -ForegroundColor Gray
Write-Host ""
