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

### 11. Migrated to WSL2 Ollama + `OLLAMA_BASE_URL` Support
- Installed WSL2 Ubuntu with GPU passthrough (NVIDIA CUDA 13.0 on Linux)
- Installed Ollama 0.23.2 in WSL2 (Linux CUDA, not Windows WDDM)
- Added `OLLAMA_BASE_URL` env var to `llm/inference.py` so workers can point to WSL2's Ollama
- Configured Ollama with `OLLAMA_NUM_PARALLEL=4` for concurrent GPU request processing
- Configured `OLLAMA_MAX_LOADED_MODELS=2` to keep embedding + LLM models loaded simultaneously

---

## Current Situation

### GPU Status

| Check | Result |
|-------|--------|
| GPU available | ✅ NVIDIA GeForce RTX 3050 Ti Laptop GPU (4GB VRAM) |
| CUDA driver | ✅ Version 13.0 (via NVIDIA driver 581.83) |
| Ollama runtime | ✅ **WSL2 (Linux CUDA)** — not Windows WDDM |
| Ollama version | ✅ **0.23.2** (vs 0.23.0 on Windows) |
| GPU compute utilization | ✅ **Active** — model loaded at 100% GPU |
| Concurrency config | ✅ `OLLAMA_NUM_PARALLEL=4`, `OLLAMA_MAX_LOADED_MODELS=2` |

### Performance Profile

**Ollama via WSL2 (Linux CUDA) — Python httpx from Windows:**

| Scenario | Warm latency |
|----------|-------------|
| Embedding (nomic-embed-text) | ~**0.03s** |
| LLM short prompt | **0.12-0.30s** |
| Full RAG pipeline (embed + LLM) | **0.31-0.40s** |
| 4 concurrent LLM requests (parallel GPU) | **~0.50s each** (all finish together) |

**System benchmark results (`--direct` mode, Windows → WSL2 Ollama):**

| Test | Avg latency | P50 | P95 | Throughput |
|------|-----------|-----|-----|-----------|
| **1 worker, 1 concurrency, 5 req** | **0.43s** | 0.32s | 0.42s | 2.17 rps |
| 4 workers, 1 concurrency, 20 req | **0.86s** | 0.67s | 2.41s | 1.14 rps |
| 4 workers, 2 concurrency, 20 req | 1.08s | 0.97s | 1.59s | 1.78 rps |
| 4 workers, 4 concurrency, 20 req | 2.27s | 1.44s | 5.32s | 1.66 rps |

**Comparison: Windows WDDM vs WSL2 Linux CUDA (1 worker)**

| Metric | Windows Ollama | WSL2 Ollama | Improvement |
|--------|---------------|-------------|-------------|
| Single LLM request | 0.31-0.77s | **0.12-0.30s** | 2-3x faster |
| Single RAG request | 0.34-0.77s | **0.31-0.40s** | 1.5-2x faster |
| 4 concurrent LLM | avg ~1.68s (serial) | **~0.50s each (parallel)** | 3x faster |
| tok/s | ~45 | **~100-130** | 2-3x faster |

---

## Problems Found

### Problem 1: RAG Pipeline Dual-Model Bottleneck
**Symptom**: 4 concurrent RAG requests take 5-6s total instead of ~0.5s (which pure LLM achieves). The embedding step (nomic-embed-text) and generation step (smollm2:135m) compete for GPU.
**Cause**: Each RAG request requires 2 separate Ollama calls (embedding + LLM) with 2 different models. Even with `OLLAMA_MAX_LOADED_MODELS=2` and `OLLAMA_NUM_PARALLEL=4`, switching between models and CPU-side ChromaDB search creates contention.
**Impact**: RAG latency scales poorly with concurrency. Pure LLM is 0.5s for 4 concurrent; RAG is 2.3-5.3s.
**Workarounds**:
- Use **concurrency=1** with 4 workers: avg **0.86s** (under 1s)
- Use **concurrency=2** with 4 workers: avg **1.08s** (p50 0.97s, close to target)
- Increase embedding cache size for repeated queries

### Problem 2: NGINX Path Unreliable
**Symptom**: Benchmark results via NGINX showed 2-3.6s, while `--direct` mode shows 0.43s (1 worker) and 0.86s (4 workers, concurrency 1).
**Mitigation**: `benchmark.py --direct` is the primary benchmark path. NGINX is not needed for single-GPU setup.
**Status**: Low priority — NGINX matters only for multi-GPU or production deployment.

### Problem 3: Ollama System Tray Auto-Restart (Windows)
**Symptom**: Windows Ollama system tray auto-restarts and competes for GPU with WSL2 Ollama.
**Fix**: Kill Windows Ollama before running benchmark. No longer needed if everything runs through WSL2.

### Problem 4: WSL2 Ollama Manual Start Required
**Symptom**: After WSL2 restart or Windows reboot, Ollama must be started manually with env vars.
**Workaround**: Configure systemd service to persist settings:
```bash
sudo systemctl edit ollama.service
# Add:
# [Service]
# Environment="OLLAMA_HOST=0.0.0.0:11434"
# Environment="OLLAMA_NUM_PARALLEL=4"
# Environment="OLLAMA_MAX_LOADED_MODELS=2"
# Environment="OLLAMA_KEEP_ALIVE=5m"
```

### Problem 5: Latency Variance (p95 >> avg)
**Symptom**: Many benchmarks show p95 much higher than avg (e.g., avg 0.86s but p95 2.41s).
**Cause**: Some requests hit model-loading edge cases, GPU scheduling variance, or ChromaDB lock contention.
**Impact**: Occasional slow requests degrade tail latency. Mitigated by concurrency=1 or pre-warming.

### Problem 6: WSL2 IP Changes on Reboot
**Symptom**: WSL2 IP (`172.18.45.44`) changes after reboot, requiring `OLLAMA_BASE_URL` update.
**Workaround**: Set static WSL2 IP in `.wslconfig` or use hostname `host.docker.internal`.

### Solved ✓
- **GPU underutilization**: WSL2 Linux CUDA gives 80-90% GPU utilization vs 6% on Windows WDDM
- **Single-GPU serialization**: `OLLAMA_NUM_PARALLEL=4` enables parallel GPU inference on Linux
- **Windows Ollama vs WSL2 competition**: Solved by killing Windows Ollama processes

---

## Conclusions

### What's Working
1. **WSL2 Ollama with Linux CUDA** — GPU utilization at 80-90%, 2-3x faster per-request than Windows WDDM
2. **Parallel GPU inference** — `OLLAMA_NUM_PARALLEL=4`: 4 concurrent LLM requests all complete in ~0.5s
3. **4 workers functional** — Correct round-robin distribution, 100% success rate
4. **Sub-second with 4 workers achievable** — concurrency=1: **avg 0.86s** (< 1s ✓)
5. **`OLLAMA_BASE_URL` env var** — Workers can target any remote Ollama instance (WSL2, remote server)
6. **Full system pipeline** — Benchmark spawns master + 4 workers, warms up, tests, cleans up

### What Needs Work
1. **RAG dual-model overhead** — Embedding + LLM in same pipeline limits concurrent throughput. Pure LLM is 0.5s for 4 concurrent; RAG is 2.3s+
2. **Latency variance** — p95 often 2-3x avg on 4-worker benchmarks due to model switching
3. **WSL2 persistence** — Ollama config/env vars lost on reboot; systemd service not yet configured
4. **WSL2 IP volatility** — IP changes on reboot; `OLLAMA_BASE_URL` must be updated
5. **Larger models untested** — Need to test smollm2:360m, qwen2.5:0.5b for latency/quality tradeoff

### The System CAN Achieve < 1s Per Request with 4 Workers
**Confirmed**: 4 workers, concurrency=1 → **avg 0.86s** (under 1s ✓). Pure LLM achieves **0.5s for 4 concurrent** on WSL2 with `OLLAMA_NUM_PARALLEL=4`. The RAG pipeline adds overhead but still hits the target at low concurrency.

---

## Next Steps

### Immediate
1. ✅ Migrated Ollama to WSL2 — Linux CUDA, 2-3x faster, true GPU parallelism
2. ✅ Added `OLLAMA_BASE_URL` env var support in `llm/inference.py`
3. ✅ Proved 4-worker sub-second latency: concurrency=1 → **avg 0.86s**
4. ✅ Configured `OLLAMA_NUM_PARALLEL=4`, `OLLAMA_MAX_LOADED_MODELS=2`

### Short-term
1. **Persist WSL2 Ollama config** — `sudo systemctl edit ollama.service` with env vars so settings survive reboot
2. **Fix WSL2 IP volatility** — Use static IP in `.wslconfig` or `host.docker.internal` hostname
3. **Optimize RAG embedding** — Pre-warm nomic-embed-text before load test; increase cache size; batch embedding calls
4. **Test larger models** — smollm2:360m, qwen2.5:0.5b for latency/quality tradeoff

### Medium-term
1. **Single-model RAG** — Replace dual-model pipeline (embed + LLM) with a single model that handles both (e.g., embedding via LLM's hidden states)
2. **Async inference engine** — Replace sync `OllamaLLM` + `ThreadPoolExecutor` with `httpx.AsyncClient` direct to Ollama API
3. **Embedding cache persistence** — Share cache across workers via Redis or file-based cache

### Long-term
1. Move entire project to WSL2 (no Windows→WSL2 network hop)
2. Multi-GPU: pin each worker to a different GPU for true horizontal scaling
3. Replace ChromaDB with FAISS or simpler in-memory index for faster retrieval
