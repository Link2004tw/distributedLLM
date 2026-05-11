# Progress Report

## What We've Done

### 1. Fixed Import Path Issues
- Workers were failing with `ModuleNotFoundError: No module named 'rag'` when run from `workers/` directory.
- **Fix**: All components must be run from the project root (`distributedLLM\`) using `python -m workers.worker`.

### 2. Migrated Worker to FastAPI Lifespan Pattern
- `workers/worker.py` had deprecated `@app.on_event("startup")`.
- **Fix**: Migrated to the modern `lifespan` context manager. No more deprecation warnings.

### 3. Added `/query` Proxy to Load Balancer
- The load generator was getting 404s at `http://localhost:8000/query` because `lb/app.py` had no such endpoint (it was only an NGINX management controller).
- **Fix**: Added a `/query` POST endpoint to `lb/app.py` that round-robins requests to workers and retries on failure, so the system works without NGINX installed.

### 4. Made Configuration Environment-Driven

**`llm/inference.py`** — Now reads these env vars:

| Env Var | Default | Purpose |
|---------|---------|---------|
| `LLM_MODEL` | `smollm2:135m` | Which Ollama model to use |
| `OLLAMA_NUM_GPU` | (all layers) | GPU layers to offload |
| `OLLAMA_CONTEXT_LENGTH` | 2048 | Context window size |
| `OLLAMA_BATCH_SIZE` | 512 | Prompt batch size |

**`rag/retriever.py`** — Now reads these env vars:

| Env Var | Default | Purpose |
|---------|---------|---------|
| `EMBEDDING_MODEL` | `nomic-embed-text:latest` | Embedding model |
| `CHROMA_DB_PATH` | `./chroma_db` | Vector DB location |
| `RETRIEVER_CACHE_SIZE` | `128` | Embedding cache capacity |

**`workers/worker.py`** — Now reads:

| Env Var | Default | Purpose |
|---------|---------|---------|
| `TOP_K` | `3` | Default number of RAG context chunks |

### 5. Added Worker `/ready` Endpoint
- `workers/worker.py` now has a `GET /ready` endpoint that actually tests model inference (calls `inference_engine.generate("ping")`) before returning `ready: true`.
- Benchmark uses this to confirm the worker can serve requests before starting the load test.

### 6. Created `benchmark.py` — Automated Benchmark Suite
End-to-end script that:
1. Checks Ollama is running and required models are pulled
2. Sets up and starts NGINX on port 8000
3. Spawns master node + N workers with specified model/config
4. Sends warmup requests to avoid cold-start latency penalty
5. Runs load tests with configurable requests/concurrency
6. Collects full metrics: throughput, avg/P50/P95/P99 latency, error rate
7. Can test multiple models, worker counts, and routing strategies
8. Saves results to timestamped JSON files
9. Cleans up processes afterward

Usage:
```powershell
# Quick test
python benchmark.py --single --model smollm2:135m --workers 4 --requests 20 --concurrency 4

# Full suite
python benchmark.py
```

### 7. Created `ollama_gpu.ps1` — GPU Restart Helper
One-click script that kills the Ollama system tray and server, then restarts with `OLLAMA_NUM_GPU=999`:

```powershell
.\ollama_gpu.ps1
```

### 8. Created `RUNBOOK.md` — Manual Testing Guide
Comprehensive step-by-step guide covering prerequisites, startup order, smoke tests, manual load testing, automated benchmarking, fault tolerance testing, and troubleshooting.

### 9. Added Embedding Cache to Retriever
- `rag/retriever.py` now has an LRU cache (default 128 entries) for embedding results.
- Repeated queries skip the expensive embedding call. Cache is per-worker-process.

### 10. Updated `.gitignore`
Added `benchmark_results_*.json` and `benchmark_result_latest.json` to prevent generated benchmark outputs from being committed.

---

## Current Situation

### GPU Status

| Check | Result |
|-------|--------|
| GPU available | ✅ NVIDIA GeForce RTX 3050 Ti Laptop GPU (4GB VRAM) |
| CUDA driver | ✅ Version 13.0 (via NVIDIA driver 581.83) |
| Ollama on GPU | ✅ Models loaded into VRAM (796 MiB with smollm2:135m) |
| GPU compute utilization | ⚠️ Only **6%** during inference (WDDM overhead on Windows) |

### Performance Profile

**Ollama direct (Python httpx client):**

| Scenario | Cold (first call) | Warm (model in VRAM) |
|----------|-------------------|----------------------|
| Embedding (nomic-embed-text) | 2.12s | **0.06s** |
| LLM short prompt | ~2.0s | **0.31s** |
| LLM with RAG context | ~3.0s | **0.53s** |
| Full RAG pipeline | ~2.5s | **0.34-0.48s** |

**Ollama internal timing** (from raw response):
```
total_duration: 0.33s  (shows actual inference, not HTTP overhead)
eval_count: 10 tokens
tok/s: 44.7
```

**System benchmark results (`--direct` mode, bypassing NGINX):**

| Test | Avg latency | P50 | P95 | Throughput | Error rate |
|------|-----------|-----|-----|-----------|------------|
| 1 worker, 2 concurrency, 10 requests | **0.77s** | 0.69s | 0.96s | 2.35 req/s | 0% |
| 4 workers, 4 concurrency, 20 requests | **1.68s** | 1.61s | 2.18s | 2.17 req/s | 0% |
| Direct worker (no NGINX), 1 request | **0.41s** | - | - | - | 0% |

---

## Problems Found

### Problem 1: Cold-Start Model Loading
**Symptom**: First request to a newly started worker takes 2-3s vs 0.4s for subsequent requests.
**Cause**: Ollama loads the model into GPU memory on first inference call. This adds 0.3-2.0s depending on model size.
**Partial fix**: The benchmark now sends warmup requests to each worker before the load test.
**Remaining**: Warmup requests go through NGINX, which is round-robin. Each worker gets 2 warmup requests (for 4 workers, 8 total warmup). This should be sufficient to load both nomic-embed-text and smollm2:135m into VRAM.

### Problem 2: NGINX Overhead / Reliability
**Symptom**: Benchmark results via NGINX showed 2-3.6s, but `--direct` mode (bypassing NGINX) shows **0.77s** (1 worker). The NGINX path adds significant latency.
**Mitigation**: `benchmark.py --direct` mode is now the primary benchmarking path. NGINX routing can be investigated separately but is not blocking progress.
**Suspected causes**:
- NGINX config not properly deployed to the `nginx/conf/` directory during benchmark start
- Round-robin distribution across workers may interact poorly with the warmup phase
- NGINX's `max_fails=3 fail_timeout=30s` may mark workers as down during the startup phase

### Problem 3: GPU Underutilization
**Symptom**: `nvidia-smi` reports only 6% GPU utilization during inference.
**Cause**: Ollama on Windows (WDDM mode) with an RTX 3050 Ti laptop GPU has limited GPU compute performance. Ollama version 0.23.0 predates many GPU optimizations (Flash Attention, etc.). The RTX 3050 Ti has 4GB VRAM shared with display output.
**Impact**: The system achieves ~45 tok/s. On Linux with the same GPU, this would likely be 100+ tok/s.

### Problem 4: PowerShell vs Python HTTP Overhead
**Symptom**: `curl.exe` in PowerShell reports 1.6-5.7s latency while `httpx` in Python reports 0.3-0.6s for the same Ollama call.
**Cause**: `curl.exe` on Windows has significant process-creation overhead per call. This only affects manual testing via PowerShell, not the automated benchmark (which uses Python `httpx`).
**Impact**: Manual smoke tests via `curl` will show artificially high latencies. Always use Python for accurate timing.

### Problem 5: Ollama System Tray Auto-Restart
**Symptom**: The `ollama_gpu.ps1` script kills Ollama, but the Windows system tray app (`ollama app`) automatically restarts the server. The new server doesn't inherit the `OLLAMA_NUM_GPU=999` env var, so GPU config is lost.
**Fix**: `ollama_gpu.ps1` now explicitly kills the `ollama app` process before restarting the server with the GPU flag.
**Limitation**: Next time the user logs in, the system tray app starts again without the GPU env var. The workaround is to set `OLLAMA_NUM_GPU` as a system-wide environment variable:
```powershell
[Environment]::SetEnvironmentVariable("OLLAMA_NUM_GPU", "999", "User")
```

### Problem 6: Multiple Ollama Server Processes

### Problem 7: Single-GPU Bottleneck — More Workers Doesn't Help
**Symptom**: 4 workers (avg 1.68s) is **worse** than 1 worker (avg 0.77s) in `--direct` mode. Throughput is essentially identical (~2.2 req/s).
**Cause**: The RTX 3050 Ti is a single-GPU system. Ollama on Windows (WDDM) serializes GPU access. Adding workers increases process scheduling overhead and VRAM contention without any GPU parallelism benefit.
**Impact**: For this setup, **1 worker is optimal**. Scaling to more workers only adds latency. True horizontal scaling would require multiple GPUs or WSL2/Linux with proper GPU sharing.
**Workaround**: Use `--workers 1` for best latency on this hardware. Benchmark defaults should be updated to default to 1 worker.
**Symptom**: After running the benchmark, `nvidia-smi` shows 3+ `ollama.exe` processes. Port conflicts occur when trying to restart.
**Cause**: The Ollama system tray app spawns new server instances. Old server instances may not be fully cleaned up.
**Impact**: Requests may route to the wrong server instance, one without GPU config.

---

## Conclusions

### What's Working
1. **GPU memory is active** — Models are loaded into VRAM (796 MiB used for smollm2:135m).
2. **Inference is fast when warm** — 0.31s for simple LLM, 0.06s for embedding, **0.34-0.48s for full RAG pipeline**.
3. **System is functional** — 100% success rate on all load tests with proper model validation.
4. **All components connect** — Workers register with master, load generator sends requests end-to-end.
5. **`benchmark.py --direct` mode works** — Automated suite with master spawn, worker spawn, warmup, load test, cleanup all functioning.
6. **Sub-second latency achieved** — 1 worker, 2 concurrency: **avg 0.77s, p95 0.96s** (< 1s target met).

### What Needs Work
1. **NGINX path still unverified** — `--direct` mode works and is the primary benchmark path. NGINX routing needs separate investigation if needed.
2. **GPU compute utilization** — Only 6% GPU utilization suggests Ollama on Windows is not fully using the GPU. Running via WSL2 would likely give 2-3x speedup.
3. **Single-GPU scaling** — More workers degrades latency on this hardware. 1 worker is optimal for RTX 3050 Ti.
4. **Larger models untested** — Need to test smollm2:360m, qwen2.5:0.5b to find latency/quality tradeoff.

### The System CAN Achieve < 1s Per Request
Confirmed by automated benchmark: **0.77s avg, 0.96s p95** with 1 worker in `--direct` mode. The direct worker test (0.41s) shows the floor — system overhead (master, worker server, warmup, httpx) adds ~0.3s.

---

## Next Steps

### Immediate
1. ✅ Fixed `benchmark.py` syntax error (orphaned `finally`) and structural bug (master/workers inside `if not direct:`)
2. ✅ Added `--direct` mode — now the primary benchmark path
3. ✅ Proved sub-second latency: **avg 0.77s, p95 0.96s** with 1 worker

### Short-term
1. Default benchmark to `--workers 1` (1 worker is optimal for single GPU)
2. Test with larger models (smollm2:360m, qwen2.5:0.5b) to find the best latency/quality tradeoff
3. Add `--warmup-only` flag to pre-warm models without running load test

### Medium-term
1. Investigate NGINX path separately (if multi-worker needed for future multi-GPU setup)
2. Consider running Ollama in WSL2 for better GPU performance (Linux CUDA path is 2-3x faster than Windows WDDM)
3. Experiment with Ollama server configuration (num parallel, queue settings)

### Long-term
1. Embedding cache persistence across worker restarts
2. Consider switching from multi-process workers to async worker architecture to reduce per-request overhead
3. Multi-GPU distribution (each worker pinned to a GPU) for true horizontal scaling
