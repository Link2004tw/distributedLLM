param(
    [switch]$SkipOllama
)

$ErrorActionPreference = "Stop"

Write-Host "=== Stopping existing services ===" -ForegroundColor Yellow

Get-Process -Name "uvicorn" -ErrorAction SilentlyContinue | Stop-Process -Force
Write-Host "Stopped existing uvicorn processes"

if (-not $SkipOllama) {
    $ollama = Get-Process -Name "ollama" -ErrorAction SilentlyContinue
    if (-not $ollama) {
        Write-Host "Starting Ollama..." -ForegroundColor Yellow
        Start-Process ollama -ArgumentList "serve" -NoNewWindow
        Start-Sleep -Seconds 5
        Write-Host "Ollama started"
    } else {
        Write-Host "Ollama already running"
    }
}

Write-Host ""
Write-Host "=== Starting services ===" -ForegroundColor Green

$workers = @(
    @{ Id = "worker-1"; Port = 8001; Ollama = "http://localhost:11434" },
    @{ Id = "worker-2"; Port = 8002; Ollama = "http://localhost:11435" },
    @{ Id = "worker-3"; Port = 8003; Ollama = "http://localhost:11436" },
    @{ Id = "worker-4"; Port = 8004; Ollama = "http://localhost:11434" }
)

foreach ($w in $workers) {
    Write-Host "Starting $($w.Id) on port $($w.Port)..."
    $cmd = "cd 'E:\coding\python\distributed'; " +
           "`$env:WORKER_ID='$($w.Id)'; " +
           "`$env:PORT='$($w.Port)'; " +
           "`$env:OLLAMA_URL='$($w.Ollama)'; " +
           "`$env:MAX_CONCURRENT_TASKS='4'; " +
           "uvicorn workers.worker:app --port $($w.Port) --host 127.0.0.1"
    Start-Process powershell -ArgumentList "-NoExit", "-Command", $cmd
}

Write-Host "Starting Master node on port 9000..."
$cmd = "cd 'E:\coding\python\distributed'; uvicorn master.monitor:app --port 9000 --host 127.0.0.1"
Start-Process powershell -ArgumentList "-NoExit", "-Command", $cmd

Write-Host "Starting Load Balancer on port 8000..."
$cmd = "cd 'E:\coding\python\distributed'; uvicorn lb.load_balancer:app --port 8000 --host 127.0.0.1"
Start-Process powershell -ArgumentList "-NoExit", "-Command", $cmd

Write-Host ""
Write-Host "=== Waiting for services to initialize (10 seconds) ===" -ForegroundColor Cyan
Start-Sleep -Seconds 10

Write-Host ""
Write-Host "=== Service Status ===" -ForegroundColor Green

$services = @(
    @{ Name = "Load Balancer"; Url = "http://localhost:8000/health" },
    @{ Name = "Master Node"; Url = "http://localhost:9000/health" },
    @{ Name = "Worker-1"; Url = "http://localhost:8001/health" },
    @{ Name = "Worker-2"; Url = "http://localhost:8002/health" },
    @{ Name = "Worker-3"; Url = "http://localhost:8003/health" },
    @{ Name = "Worker-4"; Url = "http://localhost:8004/health" }
)

$client = New-Object System.Net.Http.HttpClient
$client.Timeout = New-Object System.TimeSpan(0, 0, 5)

foreach ($s in $services) {
    try {
        $resp = $client.GetAsync($s.Url).Result
        if ($resp.IsSuccessStatusCode) {
            Write-Host "[OK] $($s.Name)" -ForegroundColor Green
        } else {
            Write-Host "[FAIL] $($s.Name) - $($resp.StatusCode)" -ForegroundColor Red
        }
    } catch {
        Write-Host "[DOWN] $($s.Name)" -ForegroundColor Red
    }
}

Write-Host ""
Write-Host "=== Ready to test ===" -ForegroundColor Cyan
Write-Host "Run: pytest tests/test_load_balancer.py::TestConcurrentRequestHandling -v"
