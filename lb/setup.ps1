param(
    [string]$NginxVersion = "1.26.0"
)

$NginxUrl = "https://nginx.org/download/nginx-$NginxVersion.zip"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$NginxDir = "$ScriptDir\nginx"
$ConfSource = "$ScriptDir\nginx.conf"
$ConfDest = "$NginxDir\conf\nginx.conf"

Write-Host "=== NGINX Setup for Distributed LLM System ===" -ForegroundColor Cyan

if (-not (Test-Path "$NginxDir\nginx.exe")) {
    Write-Host "[1/3] Downloading NGINX $NginxVersion..." -ForegroundColor Yellow
    $zipPath = "$env:TEMP\nginx.zip"
    try {
        Invoke-WebRequest -Uri $NginxUrl -OutFile $zipPath -UseBasicParsing
    } catch {
        Write-Host "  Download failed: $_" -ForegroundColor Red
        Write-Host "  Download manually from: $NginxUrl" -ForegroundColor Yellow
        Write-Host "  Extract to: $NginxDir" -ForegroundColor Yellow
        exit 1
    }
    Expand-Archive -Path $zipPath -DestinationPath $env:TEMP -Force
    New-Item -ItemType Directory -Path $NginxDir -Force | Out-Null
    Copy-Item -Path "$env:TEMP\nginx-$NginxVersion\*" -Destination $NginxDir -Recurse -Force
    Remove-Item $zipPath
    Write-Host "  Extracted to: $NginxDir" -ForegroundColor Green
} else {
    Write-Host "[1/3] NGINX already present" -ForegroundColor Green
}

Write-Host "[2/3] Deploying nginx.conf..." -ForegroundColor Yellow
Copy-Item -Path $ConfSource -Destination $ConfDest -Force
Write-Host "  Config placed at: $ConfDest" -ForegroundColor Green

Write-Host "[3/3] Starting NGINX..." -ForegroundColor Yellow
$existing = Get-Process -Name "nginx" -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host "  NGINX already running. Reloading..." -ForegroundColor Yellow
    & "$NginxDir\nginx.exe" -p "$NginxDir" -s reload
} else {
    & "$NginxDir\nginx.exe" -p "$NginxDir"
    Start-Sleep -Seconds 1
}

$proc = Get-Process -Name "nginx" -ErrorAction SilentlyContinue
if ($proc) {
    Write-Host "  NGINX started (PID: $($proc.Id))" -ForegroundColor Green
    Write-Host "  Listening on port 8000" -ForegroundColor Green
} else {
    Write-Host "  NGINX failed to start. Check $NginxDir\logs\error.log" -ForegroundColor Red
    exit 1
}

Write-Host "=== Setup Complete ===" -ForegroundColor Cyan
Write-Host ""
Write-Host "Test with:"
Write-Host "  curl http://localhost:8000/health"
Write-Host "  curl http://localhost:8000/nginx_status"
Write-Host ""
Write-Host "Useful commands (must use -p flag):"
Write-Host "  nginx -p lb/nginx -s reload    (after config changes)"
Write-Host "  nginx -p lb/nginx -s quit      (stop gracefully)"
Write-Host "  nginx -p lb/nginx -t           (test config)"
