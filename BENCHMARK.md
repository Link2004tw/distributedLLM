# Benchmark Guide

All commands run from `distributedLLM\` root using `.venv\Scripts\python.exe`.

---

## 1. One-Time Setup

### 1.1 Pull Ollama models (inside WSL2)
```bash
ollama pull nomic-embed-text
ollama pull smollm2:135m
```

### 1.2 Configure WSL2 Ollama for parallel processing
```bash
sudo systemctl edit ollama.service
```
Add under `[Service]`:
```
Environment="OLLAMA_NUM_PARALLEL=4"
Environment="OLLAMA_MAX_LOADED_MODELS=2"
Environment="OLLAMA_KEEP_ALIVE=5m"
Environment="OLLAMA_HOST=0.0.0.0:11434"
```
Then:
```bash
sudo systemctl daemon-reload
sudo systemctl restart ollama.service
```

### 1.3 Ingest documents (run once from Windows)
```powershell
.venv\Scripts\python.exe ingest.py
```

---

## 2. Pre-Benchmark Checklist

### 2.1 Kill Windows Ollama (competes for GPU)
```powershell
taskkill /f /im ollama.exe
```

### 2.2 Verify WSL2 Ollama is reachable from Windows
```powershell
curl.exe -s http://localhost:11434/api/tags
```
Expected: JSON list with `nomic-embed-text` and `smollm2:135m`.

### 2.3 Verify GPU is available in WSL2
```powershell
wsl.exe nvidia-smi
```

---

## 3. Running Benchmarks

### 3.1 Quick smoke test (10 requests, 2 workers)
```powershell
.venv\Scripts\python.exe benchmark.py --requests 10 --workers 2 --concurrency 4 --direct --single
```

### 3.2 Standard benchmark (100 requests, 4 workers)
```powershell
.venv\Scripts\python.exe benchmark.py --requests 100 --workers 4 --concurrency 10 --direct --single
```

### 3.3 Heavy benchmark (1000 requests, 4 workers)
```powershell
.venv\Scripts\python.exe benchmark.py --requests 1000 --workers 4 --concurrency 20 --direct --single
```
> Takes ~7-8 minutes. Steady-state throughput ~2-3 req/s on RTX 3050 Ti.

### 3.4 Benchmark with different model
```powershell
.venv\Scripts\python.exe benchmark.py --requests 100 --workers 4 --concurrency 10 --direct --single --model smollm2:360m
```

### 3.5 Full suite (all models x worker counts x strategies)
```powershell
.venv\Scripts\python.exe benchmark.py --requests 100 --direct
```

### 3.6 Via NGINX (slower, includes LB hop)
```powershell
.venv\Scripts\python.exe benchmark.py --requests 100 --workers 4 --concurrency 10 --single
```

---

## 4. Flag Reference

| Flag | Default | Description |
|------|---------|-------------|
| `--requests` | 100 | Total requests per test |
| `--workers` | 1,2,4 | Number of worker processes |
| `--concurrency` | 10,50 | Concurrent client threads |
| `--direct` | off | Bypass NGINX, send directly to workers |
| `--single` | off | Run one test and exit (vs suite) |
| `--model` | all | Specific model to test (e.g. `smollm2:135m`) |
| `--num-gpu` | default | `OLLAMA_NUM_GPU` layers |
| `--ctx` | 2048 | `OLLAMA_CONTEXT_LENGTH` |
| `--batch` | 512 | `OLLAMA_BATCH_SIZE` |
| `--embedding-model` | `nomic-embed-text:latest` | Embedding model for retrieval |

---

## 5. Reading Results

Output example:
```
--- single-test ---
  Success: 999/1000  |  Error rate: 0.1%
  Throughput: 2.22 req/s  |  Total time: 450.59s
  Latency: avg=8.7915s  p50=8.0342s  p95=15.9521s  p99=18.5976s
```

Key metrics:
- **Throughput**: requests per second (higher is better)
- **Avg latency**: mean response time (lower is better)
- **P50/P95/P99**: percentile latencies — P99 < 1s is the target
- **Error rate**: % of failed requests (should be < 1%)

Results are also saved to `benchmark_results_{timestamp}.json`.

---

## 6. Monitoring During a Run

Open a second PowerShell to watch GPU utilization:
```powershell
wsl.exe nvidia-smi --query-gpu=utilization.gpu,memory.used --format=csv -l 2
```

Expected: GPU utilization 40-60% during active inference, 0% during ChromaDB phases.

---

## 7. Troubleshooting

| Symptom | Fix |
|---------|-----|
| `ollama.exe` consuming GPU | `taskkill /f /im ollama.exe` |
| Worker not ready | Check WSL2 Ollama is running: `wsl.exe curl -s http://localhost:11434/api/tags` |
| All requests time out | Increase `--concurrency` or reduce `--requests` |
| Port already in use | `taskkill /f /im python.exe` then retry |
| `ModuleNotFoundError` | Run from `distributedLLM\` root directory |
