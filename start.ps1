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

# Clean up OLLAMA_HOST so Python Ollama client connects to localhost, not 0.0.0.0
Remove-Item Env:\OLLAMA_HOST -ErrorAction SilentlyContinue

Write-Host "=== Starting Worker Node: $WorkerId ===" -ForegroundColor Cyan
Write-Host "Master node: $masterIp"
Write-Host "Worker port: $Port"
Write-Host "Ollama port: $OllamaPort"
Write-Host ""

# Start Ollama
Write-Host "[1/3] Starting Ollama on port $OllamaPort..." -ForegroundColor Yellow
$ollamaAlive = $false
try {
    $null = Invoke-WebRequest -Uri "http://localhost:$OllamaPort/api/version" -TimeoutSec 3 -UseBasicParsing -ErrorAction Stop
    $ollamaAlive = $true
} catch {}

if (-not $ollamaAlive) {
    Write-Host "  Ollama not responding, starting it..." -ForegroundColor Yellow
    Get-Process -Name "ollama" -ErrorAction SilentlyContinue | Stop-Process -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 1
    $env:OLLAMA_HOST = "0.0.0.0:$OllamaPort"
    Start-Process ollama -ArgumentList "serve" -NoNewWindow
    Remove-Item Env:\OLLAMA_HOST -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 5
} else {
    Write-Host "  Ollama already running on port $OllamaPort" -ForegroundColor Gray
}

Start-Sleep -Seconds 2

# Pull model if not already present
$ErrorActionPreference = "Continue"
$hasModel = ollama list 2>$null | Select-String $OllamaModel
$ErrorActionPreference = "Stop"
if (-not $hasModel) {
    Write-Host "[2/3] Pulling model $OllamaModel..." -ForegroundColor Yellow
    $ErrorActionPreference = "Continue"
    ollama pull $OllamaModel
    $ErrorActionPreference = "Stop"
} else {
    Write-Host "[2/3] Model $OllamaModel already downloaded" -ForegroundColor Gray
}
Write-Host "  Model ready." -ForegroundColor Green

# Kill stale worker on this port
$stalePid = (netstat -ano | Select-String ":$Port\s+.*LISTENING" | ForEach-Object { $_ -replace '.*\s+(\d+)$', '$1' } | Select-Object -First 1)
if ($stalePid) {
    Write-Host "  Port $Port in use by PID $stalePid, stopping it..." -ForegroundColor Yellow
    Stop-Process -Id $stalePid -Force -ErrorAction SilentlyContinue
    Start-Sleep -Seconds 2
}

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
