param(
    [int]$Count = 4,
    [int]$WorkerStartPort = 8001,
    [int]$OllamaStartPort = 11435
)

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$RootDir = Split-Path -Parent $ScriptDir

Write-Host "=== Starting $Count Workers ===" -ForegroundColor Cyan

for ($i = 1; $i -le $Count; $i++) {
    $workerPort = $WorkerStartPort + $i - 1
    $ollamaPort = $OllamaStartPort + $i - 1

    $env:WORKER_ID = "worker-$i"
    $env:PORT = $workerPort.ToString()
    $env:OLLAMA_URL = "http://localhost:$ollamaPort"

    $job = Start-Job -ScriptBlock {
        param($rootDir, $workerId, $port, $ollamaUrl)

        $env:WORKER_ID = $workerId
        $env:PORT = $port
        $env:OLLAMA_URL = $ollamaUrl

        Set-Location $rootDir
        & ".venv\Scripts\python.exe" -m uvicorn workers.worker:app --port $port
    } -ArgumentList $RootDir, "worker-$i", $workerPort.ToString(), "http://localhost:$ollamaPort"

    Write-Host "Started worker-$i on port $workerPort -> Ollama port $ollamaPort" -ForegroundColor Green
}

Write-Host ""
Write-Host "All workers started" -ForegroundColor Cyan