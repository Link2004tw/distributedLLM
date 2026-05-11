# Project Task List

## Status Legend
- [x] Completed
- [ ] Pending
- [ ] In Progress

---

## Tasks

### Phase 1: Core Infrastructure (Original)

| # | Task | Difficulty |
|---|------|------------|
| 1 | Create `workers/gpu_worker.py` - GPUWorker class with RAG + LLM pipeline | Medium |
| 2 | Refactor `lb/load_balancer.py` to FastAPI with Round Robin + Least Connections + Hybrid strategies | High |
| 3 | Implement Hybrid routing (Least Connections primary + RR tiebreaker) | High |
| 4 | Add runtime strategy switching endpoint to LB (`GET /strategy`, `POST /strategy`) | Medium |
| 5 | Add retry logic on worker failure in LB | Medium |
| 6 | Create `dashboard/` - Admin dashboard hitting Master `/metrics` and `/workers` APIs | Medium |
| 7 | Write automated fault tolerance test (kill a worker mid-test) | High |
| 8 | Smoke test all components with 10 manual requests | Low |
| 9 | Load test at 100/500/1000 users with metrics collection | High |

### Phase 2: GPU Optimization

| # | Task | Difficulty | Status |
|---|------|------------|--------|
| 10 | Verify Ollama GPU mode works (nvidia-smi check) | Low | [x] |
| 11 | Add GPU monitoring to worker `/health` endpoint (nvidia-smi parsing) | Medium | [x] |
| 12 | Create `GPUWorker` class with batch processing (batch size 10-20) | High | [x] |
| 13 | Add LRU cache for embeddings (500 items) | Medium | [x] |
| 14 | Add response cache for duplicate queries (500 items) | Medium | [x] |
| 15 | Replace ThreadPoolExecutor with asyncio (2 async tasks per worker) | Medium | [x] |
| 16 | Add concurrent Ollama client with connection pooling | Medium | [x] |
| 17 | Add batch embedding queue (flush every 100ms) | High | [x] |
| 18 | Add batch inference queue (flush every 100ms) | High | [x] |
| 19 | Refactor LB to FastAPI (replace NGINX, async routing) | High | [x] |
| 20 | Add GPU-aware routing to LB | High | [x] |
| 21 | Add response streaming support | Medium | [ ] |

### Phase 3: GPU Worker Files Created

| File | Description |
|------|-------------|
| `workers/gpu_worker.py` | Main GPU-accelerated worker with FastAPI |
| `workers/gpu_utils.py` | GPU detection and monitoring utilities |
| `llm/gpu_inference.py` | Ollama client, batch processor, LRU cache |

### Phase 4: FastAPI Load Balancer (Completed)

| File | Description |
|------|-------------|
| `lb/load_balancer.py` | Async FastAPI LB with 4 routing strategies |

### Phase 5: Test Suite

| File | Description |
|------|-------------|
| `tests/conftest.py` | Shared pytest fixtures |
| `tests/test_gpu_worker.py` | GPU worker endpoint tests |
| `tests/test_load_balancer.py` | Load balancer tests |
| `tests/test_ollama.py` | Ollama integration tests |
| `tests/run_tests.bat` | Windows test runner |
| `requests/*.http` | REST client request files |

---

## Implementation Order (Recommended)

1. Verify Ollama GPU mode (DONE)
2. Add GPU monitoring to `/health` endpoint
3. Create `GPUWorker` class with batch processing
4. Add caching layer (embeddings + responses)
5. Replace ThreadPool with asyncio
6. Refactor LB to FastAPI
7. Add GPU-aware routing
8. Add streaming support

---

## Configuration

| Setting | Value |
|---------|-------|
| GPU | RTX 3060 Laptop (6GB VRAM) |
| Workers | 4-6 (using gpu_worker.py) |
| Max Concurrent | 2 async tasks per worker |
| Batch size | 10 |
| Cache size | 500 items (LRU) |
| Ollama port | 11434 |
| LLM Model | smollm2:135m |

## GPU Worker Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /health` | GPU utilization, memory, cache stats |
| `GET /gpu-stats` | Detailed GPU metrics (util, memory, temp, power) |
| `POST /query` | Single query with caching |
| `POST /query/batch` | Batch query processing |
| `GET /capabilities` | Worker capabilities |