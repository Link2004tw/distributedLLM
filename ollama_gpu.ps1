param([string]$NumGPU = "999")

$ErrorActionPreference = "Stop"
$env:OLLAMA_NUM_GPU = $NumGPU

Write-Host "=== Ollama GPU Restart ===" -ForegroundColor Cyan
Write-Host "Setting OLLAMA_NUM_GPU=$NumGPU" -ForegroundColor Yellow

Write-Host "Killing Ollama system tray..." -ForegroundColor Yellow
Get-Process -Name "ollama app" -ErrorAction SilentlyContinue | ForEach-Object {
    taskkill /f /pid $_.Id 2>&1 | Out-Null
}
Start-Sleep -Seconds 1

Write-Host "Killing Ollama server..." -ForegroundColor Yellow
Get-Process -Name "ollama" -ErrorAction SilentlyContinue | ForEach-Object {
    taskkill /f /pid $_.Id 2>&1 | Out-Null
}
Start-Sleep -Seconds 2

Write-Host "Waiting for port 11434..." -ForegroundColor Yellow
for ($i = 0; $i -lt 15; $i++) {
    $conn = netstat -ano | findstr ":11434"
    if (-not $conn) {
        Write-Host "  Port free" -ForegroundColor Green
        break
    }
    $parts = $conn.Split(" ", [StringSplitOptions]::RemoveEmptyEntries)
    $hpid = $parts[$parts.Length - 1]
    taskkill /f /pid $hpid 2>&1 | Out-Null
    Start-Sleep -Seconds 1
}

Write-Host "Starting Ollama..." -ForegroundColor Yellow
$p = Start-Process -FilePath "ollama.exe" -ArgumentList "serve" -WindowStyle Hidden -PassThru
Start-Sleep -Seconds 5

if ($p.HasExited) {
    Write-Host "FAILED: Ollama exited immediately." -ForegroundColor Red
    exit 1
}

Write-Host "Ollama started (PID: $($p.Id))" -ForegroundColor Green
Write-Host "Verify: nvidia-smi" -ForegroundColor Cyan
Write-Host "=== Done ===" -ForegroundColor Cyan
