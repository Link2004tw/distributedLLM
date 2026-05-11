param(
    [int]$Count = 4,
    [int]$StartPort = 11434
)

$OllamaPath = "C:\Users\Link\AppData\Local\Programs\Ollama\ollama.exe"
$BaseModelsDir = "E:\coding\python\distributed\ollama_models"

Write-Host "=== Starting $Count Ollama Servers ===" -ForegroundColor Cyan

for ($i = 1; $i -le $Count; $i++) {
    $port = $StartPort + $i - 1
    $modelsDir = "$BaseModelsDir\ollama_$i"
    $env:OLLAMA_MODELS = $modelsDir
    $env:OLLAMA_PORT = $port.ToString()

    if (-not (Test-Path $modelsDir)) {
        New-Item -ItemType Directory -Path $modelsDir -Force | Out-Null
    }

    $proc = Start-Process -FilePath $OllamaPath -ArgumentList "serve" -WindowStyle Hidden -PassThru -RedirectStandardOutput "$BaseModelsDir\stdout_$i.log" -RedirectStandardError "$BaseModelsDir\stderr_$i.log"

    Write-Host "Started Ollama instance $i on port $port (PID: $($proc.Id))" -ForegroundColor Green
    Write-Host "  Models dir: $modelsDir" -ForegroundColor Gray
}

Write-Host ""
Write-Host "=== Ollama Servers Running ===" -ForegroundColor Cyan
Write-Host "Ports: $StartPort through $((Get-Command $OllamaPath; $StartPort + $Count - 1))" -ForegroundColor Green
Write-Host ""
Write-Host "Test with:" -ForegroundColor Yellow
for ($i = 1; $i -le $Count; $i++) {
    $port = $StartPort + $i - 1
    Write-Host "  curl http://localhost:$port/api/tags" -ForegroundColor Gray
}