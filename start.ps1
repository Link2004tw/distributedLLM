# Start Ollama instances
$env:OLLAMA_HOST="0.0.0.0:11434"; Start-Process ollama -ArgumentList "serve" -NoNewWindow
$env:OLLAMA_HOST="0.0.0.0:11435"; Start-Process ollama -ArgumentList "serve" -NoNewWindow
$env:OLLAMA_HOST="0.0.0.0:11436"; Start-Process ollama -ArgumentList "serve" -NoNewWindow

Start-Sleep -Seconds 3

# Pull model (only needed once)
ollama -H localhost:11434 pull qwen3:8b
ollama -H localhost:11435 pull qwen3:8b
ollama -H localhost:11436 pull qwen3:8b

# Start workers
$env:WORKER_ID="worker-1"; $env:PORT="8001"; $env:OLLAMA_URL="http://localhost:11434"
Start-Process uvicorn -ArgumentList "worker:app --port 8001" -NoNewWindow

$env:WORKER_ID="worker-2"; $env:PORT="8002"; $env:OLLAMA_URL="http://localhost:11435"
Start-Process uvicorn -ArgumentList "worker:app --port 8002" -NoNewWindow

$env:WORKER_ID="worker-3"; $env:PORT="8003"; $env:OLLAMA_URL="http://localhost:11436"
Start-Process uvicorn -ArgumentList "worker:app --port 8003" -NoNewWindow

Write-Host "All workers started"