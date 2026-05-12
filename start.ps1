param(
    [string]$WorkerId = "worker-1",
    [string]$Port = "8001",
    [string]$OllamaPort = "11434",
    [string]$OllamaModel = "smollm:135m"
)

$ErrorActionPreference = "Stop"

# Load MASTER IP from .env
$envFile = Join-Path $PSScriptRoot ".env"
if (Test-Path $envFile) {
    Get-Content $envFile | ForEach-Object {
        if ($_ -match '^MASTER=(.+)') {
            $env:MASTER_IP = $matches[1]
        }
    }
}

$masterIp = $env:MASTER_IP
if (-not $masterIp) {
    $masterIp = "localhost"
    Write-Host "WARNING: MASTER not found in .env, falling back to localhost" -ForegroundColor Yellow
}

Write-Host "=== Starting Worker Node: $WorkerId ===" -ForegroundColor Cyan
Write-Host "Master node: $masterIp"
Write-Host "Worker port: $Port"
Write-Host "Ollama port: $OllamaPort"
Write-Host ""

# Start Ollama
Write-Host "[1/3] Starting Ollama on port $OllamaPort..." -ForegroundColor Yellow
$env:OLLAMA_HOST="0.0.0.0:$OllamaPort"
$ollamaProc = Get-Process -Name "ollama" -ErrorAction SilentlyContinue | Where-Object { $_.CommandLine -like "*$OllamaPort*" }
if (-not $ollamaProc) {
    Start-Process ollama -ArgumentList "serve" -NoNewWindow
    Start-Sleep -Seconds 3
} else {
    Write-Host "  Ollama already running on port $OllamaPort" -ForegroundColor Gray
}

Start-Sleep -Seconds 2

# Pull model
Write-Host "[2/3] Pulling model $OllamaModel..." -ForegroundColor Yellow
ollama pull $OllamaModel 2>$null
Write-Host "  Model ready." -ForegroundColor Green

# Start worker
Write-Host "[3/3] Starting $WorkerId on port $Port..." -ForegroundColor Yellow
$env:WORKER_ID = $WorkerId
$env:PORT = $Port
$env:OLLAMA_URL = "http://localhost:$OllamaPort"
$env:MASTER_NODE_URL = "http://${masterIp}:9000"
$env:MAX_CONCURRENT_TASKS = "20"
$env:BACKPRESSURE_QUEUE_SIZE = "200"

Start-Process uvicorn -ArgumentList "workers.worker:app --port $Port --host 0.0.0.0 --log-level warning" -NoNewWindow

Write-Host ""
Write-Host "=== Worker $WorkerId started ===" -ForegroundColor Green
Write-Host "  Worker URL: http://$(hostname):$Port"
Write-Host "  Master URL: http://${masterIp}:9000"
Write-Host "  Ollama URL: http://localhost:$OllamaPort"
