# Runbook — Manual Testing Guide

All commands run from `distributedLLM\` root unless noted.

---

## 1. Prerequisites (one-time)

### 1.1 Python environment
```powershell
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 1.2 Pull Ollama models
```powershell
ollama pull smollm2:135m
ollama pull qwen2.5:0.5b
ollama pull nomic-embed-text
```

### 1.3 Configure GPU acceleration
Set this **permanently** so Ollama always uses GPU:
```powershell
[Environment]::SetEnvironmentVariable("OLLAMA_NUM_GPU", "999", "User")
```

Then restart Ollama:
```powershell
taskkill /f /im ollama.exe
ollama serve
```

### 1.4 Verify GPU is active
```powershell
nvidia-smi
```
Expected: `ollama.exe` appears in the process list, GPU memory > 100MiB used.

### 1.5 Ingest documents into ChromaDB
```powershell
python ingest.py
```

### 1.6 Setup NGINX (first time only)
```powershell
powershell -File lb\setup.ps1
```

---

## 2. Startup Order

Open **5 separate terminals** (all from `distributedLLM\` root, all with `.venv` activated).

### Terminal 1 — NGINX Load Balancer (port 8000)
```powershell
taskkill /f /im nginx.exe 2>$null
powershell -File lb\setup.ps1
```

### Terminal 2 — Master Node (port 9000)
```powershell
python -m uvicorn master.monitor:app --port 9000
```

### Terminal 3 — Worker 1 (port 8001)
```powershell
$env:WORKER_ID="worker-1"; $env:PORT="8001"
python -m uvicorn workers.worker:app --port 8001
```

### Terminal 4 — Worker 2 (port 8002)
```powershell
$env:WORKER_ID="worker-2"; $env:PORT="8002"
python -m uvicorn workers.worker:app --port 8002
```

### Terminal 5 — Worker 3 & 4 (port 8003, 8004)
Repeat for ports 8003 and 8004 in additional terminals.

---

## 3. Smoke Tests

### 3.1 NGINX health
```powershell
curl http://localhost:8000/health
```
Expected: `OK`

### 3.2 NGINX status
```powershell
curl http://localhost:8000/nginx_status
```
Expected: Shows active connections, request count.

### 3.3 Master health
```powershell
curl http://localhost:9000/health
```

### 3.4 Worker readiness (check model is loaded)
```powershell
curl http://localhost:8001/ready
curl http://localhost:8002/ready
```
Expected: `{"ready": true, "worker_id": "worker-1"}`

### 3.5 Direct worker query
```powershell
curl -X POST http://localhost:8001/query -H "Content-Type: application/json" -d '{\"query\":\"What is distributed computing?\",\"top_k\":1}'
```
Expected: JSON with `answer`, `sources`, `latency_ms`.

### 3.6 Query via NGINX (round-robin)
```powershell
curl -X POST http://localhost:8000/query -H "Content-Type: application/json" -d '{\"query\":\"What is load balancing?\",\"top_k\":1}'
```

---

## 4. Manual Load Testing

### 4.1 Quick load test (via client)
```powershell
python client/load_generator.py --requests 50 --concurrency 10
```

### 4.2 Medium load
```powershell
python client/load_generator.py --requests 200 --concurrency 20
```

### 4.3 Heavy load
```powershell
python client/load_generator.py --requests 500 --concurrency 50
```

---

## 5. Automated Benchmarking

The benchmark script handles everything: starts NGINX, master, workers, runs tests, cleans up.

### 5.1 Single quick test
```powershell
python benchmark.py --single --model smollm2:135m --workers 4 --requests 100 --concurrency 20
```

### 5.2 Full test suite (all models x worker counts x strategies)
```powershell
python benchmark.py --requests 100
```

### 5.3 Test with GPU tuning
```powershell
python benchmark.py --single --model qwen2.5:0.5b --workers 4 --requests 100 --concurrency 20 --num-gpu 999 --ctx 2048
```

### 5.4 Compare routing strategies
```powershell
python benchmark.py --single --model smollm2:135m --workers 4 --requests 100 --concurrency 20
```
Then manually switch NGINX strategy and repeat.

---

## 6. Fault Tolerance Test

1. Keep load running: `python client/load_generator.py --requests 200`
2. **Kill Worker 1** (`Ctrl+C` in its terminal)
3. Observe: NGINX detects failure, remaining workers handle requests
4. Restart Worker 1: it re-registers with Master

---

## 7. Stop Everything

```powershell
# Kill all Python uvicorn processes
taskkill /f /im python.exe

# Stop NGINX
taskkill /f /im nginx.exe

# Stop Master if running alone
curl http://localhost:9000/shutdown -X POST 2>$null
```

---

## 8. Quick Reference

| Component | Port | Start Command |
|-----------|------|--------------|
| NGINX | 8000 | `powershell -File lb\setup.ps1` |
| Master | 9000 | `python -m uvicorn master.monitor:app --port 9000` |
| Worker N | 8001-8004 | `$env:WORKER_ID="worker-N"; $env:PORT="800N"; python -m uvicorn workers.worker:app --port 800N` |

### Available Models

| Model | Size | Pull Command |
|-------|------|-------------|
| smollm2:135m | 270 MB | `ollama pull smollm2:135m` |
| smollm2:360m | ~500 MB | `ollama pull smollm2:360m` |
| qwen2.5:0.5b | 397 MB | `ollama pull qwen2.5:0.5b` |
| nomic-embed-text | 274 MB | `ollama pull nomic-embed-text` |

### Env Vars for GPU Tuning

| Variable | Purpose | Recommended |
|----------|---------|-------------|
| `OLLAMA_NUM_GPU` | GPU layers to offload | `999` (all) |
| `OLLAMA_CONTEXT_LENGTH` | Context window size | `2048` |
| `OLLAMA_BATCH_SIZE` | Prompt batch size | `512` |
| `CUDA_VISIBLE_DEVICES` | Which GPU to use | `0` (first GPU) |

---

## 9. Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| Worker `/ready` returns `false` | Model not pulled or Ollama offline | `ollama pull <model>` then restart worker |
| 404 on `/query` via port 8000 | NGINX not running / Python LB has no `/query` | Start NGINX via `setup.ps1` |
| Slow inference (>5s per request) | GPU not utilized | Set `OLLAMA_NUM_GPU=999`, restart Ollama, verify with `nvidia-smi` |
| `ModuleNotFoundError: No module named 'rag'` | Running from wrong directory | Always run from `distributedLLM\` root |
| Port already in use | Previous process not killed | `netstat -ano \| findstr :PORT` then `taskkill /PID <id> /F` |
