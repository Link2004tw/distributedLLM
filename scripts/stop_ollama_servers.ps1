Write-Host "=== Stopping All Ollama Servers ===" -ForegroundColor Cyan

$procs = Get-Process -Name "ollama" -ErrorAction SilentlyContinue
if ($procs) {
    foreach ($p in $procs) {
        Write-Host "Stopping PID $($p.Id)" -ForegroundColor Yellow
        Stop-Process -Id $p.Id -Force
    }
    Write-Host "All Ollama processes stopped" -ForegroundColor Green
} else {
    Write-Host "No Ollama processes running" -ForegroundColor Gray
}