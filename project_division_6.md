# Project Work Division — Group of 6

## Project: Distributed LLM Inference System with RAG and Load Balancing
### Ain Shams University — CSE354: Distributed Computing 2 — Semester 2025/2026

---

## System Architecture Overview

All components interact as follows:

```
                     ┌──────────────────────────────────────────┐
                     │  Master (port 9000)                      │
                     │  • Worker registry & heartbeat monitor   │
                     │  • /schedule — recommends which worker   │
                     └────┬─────────────────────────────────────┘
       POST /register     │   GET /schedule (advisory only)
          ┌───────────────┴───────────────┐
          ▼                               ▼
 Workers (8001-8004)           LB / Nginx (port 8000)
 ┌──────────────────┐    ┌───────────────────────────────┐
 │ • RAG + LLM      │◄───│ • Proxies requests to workers │
 │ • Query pipeline  │    │ • Retries, failover, queue   │
 │ • GPU stats       │    │ • Consults master if enabled │
 └──────────────────┘    └───────────┬───────────────────┘
                                     │
                              ┌──────▼──────┐
                              │  Dashboard  │
                              │  (port 8100)│
                              └─────────────┘
```

- **Nginx** (when installed) serves port 8000 as a simple round-robin reverse proxy — no advanced strategies.
- **Python LB** (fallback when nginx absent) serves port 8000 with full 5-strategy routing, retries, pending queue.
- The **Master** is an advisor only: the LB calls `POST /schedule` to ask "which worker?", but the LB itself does all actual request forwarding.
- When `USE_MASTER_SCHEDULING=0`, the LB runs its own built-in strategies and never talks to the master.
- Workers register with the master via `POST /register` on startup, but the LB discovers workers independently (hardcoded defaults + `/workers/add` API).

---

## Role Assignment

### 👤 Person 1 — Load Balancer (`lb/`)

**Files owned:** `lb/load_balancer.py` (~660 lines), `lb/app.py`

**What you actually do in the system:**
You build the system's **front door** — every client request hits port 8000, and your code decides where it goes next. When a `POST /query` arrives, your `select_worker()` function picks a healthy worker using one of 5 strategies (round-robin, least-connections, hybrid, GPU-aware, load-aware), then `forward_to_worker()` proxies the request there. If the worker fails, your code retries up to 3 times with exponential backoff, reassigns to a different worker, and if all paths fail, saves the request to `pending_requests.json` for later retry. Without your LB, no request reaches any worker.

**Details of what happens at runtime:**
1. Client sends `POST /query` to port 8000 → your `handle_query()` receives it.
2. `select_worker()` checks `USE_MASTER_SCHEDULING`. If enabled (default), calls master's `POST /schedule` to ask "which worker?" (cached for 0.5s). Falls back to local strategy if master is down.
3. `forward_to_worker()` sends the request to the chosen worker's `POST /query`.
4. If the worker returns an error or times out → retry up to 3 times on the same worker (0.5s, 1s, 1.5s backoff).
5. If all 3 retries fail → call `select_worker(exclude={failed_worker})` to pick another worker.
6. If reassignment also fails → save to `pending_requests.json` (persistent queue on disk).
7. Background `health_check_loop()` polls every 5s — marks workers unhealthy after 10 consecutive failures.
8. Background `pending_retry_loop()` retries saved requests every 5s against healthy workers (up to 5 attempts each).
9. `MAX_CONCURRENT_REQUESTS = 1000` semaphore blocks excess requests → returns 503.
10. `POST /strategy` changes routing at runtime. `GET /stats` returns latency percentiles (p50/p75/p90/p95/p99), per-worker throughput, error rates.

---

### 👤 Person 2 — GPU Worker Node (`workers/`)

**Files owned:** `workers/worker.py`

**What you actually do in the system:**
You build the component that **actually generates answers**. When the LB forwards a request to your worker, your code runs the full pipeline: enforce backpressure → check response cache → retrieve relevant documents via RAG → call Ollama for LLM inference → return the answer. Without your worker, no inference happens.

**Details of what happens at runtime:**
1. Worker starts up: creates httpx client, initializes `InferenceEngine` (connects to Ollama), calls `POST {MASTER_NODE_URL}/register` to announce itself to the master (port 9000) with its `worker_id` and `port`.
2. When `POST /query` arrives from the LB:
   - Check `active_connections >= BACKPRESSURE_QUEUE_SIZE (1000)` → return 503 if saturated.
   - Acquire `asyncio.Semaphore(250)` slot (limits concurrent tasks per worker).
   - Check LRU response cache (500 entries) → return cached answer if found (93% hit rate at 100 concurrency).
   - Call `retriever.retrieve(query, top_k=3)` which embeds the query via Ollama's `nomic-embed-text`, searches ChromaDB, and returns relevant document chunks (with its own embedding cache of 500 entries).
   - Call `InferenceEngine.generate_with_context(query, docs)` which constructs a prompt like `"Context: {docs}\n\nQuery: {query}\n\nAnswer:"` and sends it to Ollama's `/api/generate` via the shared 20-concurrent-call semaphore.
   - Return `{answer, sources, latency_ms, cache_hit, worker_id}`.
3. `/health` returns GPU stats (utilization, memory, temperature, power via `nvidia-smi`), active connections, avg latency — polled by both master and LB independently every 5s.
4. `/query/batch` splits queries into cache-hits (returned directly) and cache-misses (sent to batch Ollama inference).
5. `/query/stream` sends SSE tokens as Ollama generates them.

---

### 👤 Person 3 — Master Node + Scheduling (`master/`)

**Files owned:** `master/monitor.py`

**What you actually do in the system:**
You build the system's **registry and scheduling advisor**. Your master tracks which workers are alive (heartbeat monitoring), stores their metadata, and exposes a `/schedule` endpoint that the LB consults to decide which worker gets the next request. You do NOT proxy requests yourself — you only answer "which worker should handle this?" The LB calls your `/schedule`, gets back a worker URL, and does the actual forwarding.

**Important:** Nginx is not involved here. When nginx is installed, it acts as a simple round-robin reverse proxy with no strategy support. The advanced routing (least-connections, GPU-aware, load-aware) only happens through the Python LB, which optionally delegates the "which worker?" decision to your master via `USE_MASTER_SCHEDULING`.

**Details of what happens at runtime:**
1. Workers call `POST /register` on startup → your code stores their `WorkerInfo` (worker_id, host, port, capabilities) in `REGISTERED_WORKERS` dict.
2. Background `heartbeat_monitor()` runs every 5 seconds:
   - Polls each registered worker's `GET /health` endpoint.
   - Updates `healthy`, `active_connections`, `avg_latency_ms`, `last_heartbeat` fields.
   - After 3 consecutive missed heartbeats → adds to `FAILED_WORKERS` set → calls LB's `POST /worker/unhealthy` to notify it.
3. When LB calls `POST /schedule` with a strategy name and optional `exclude_workers`:
   - Your code runs one of 5 selection algorithms across healthy workers:
     - `round_robin` → picks by index from worker list (incrementing counter).
     - `least_connections` → picks the worker with fewest `active_connections`.
     - `load_aware` → score = `connections×30 + latency×10` (lower is better).
     - `gpu_aware` → score = `connections×10 + latency×5` (lower is better).
     - `hybrid` → groups by connection count, round-robins within the least-busy group.
   - Returns `{worker_id, host, port}`. The LB caches this for 0.5 seconds.
4. `GET /metrics` aggregates all workers' health, active connections, avg latency into a `MetricsSummary`.
5. `DELETE /worker/{id}` removes a worker from the registry.

---

### 👤 Person 4 — RAG System (`rag/`, `ingest.py`, `docs/`)

**Files owned:** `rag/retriever.py`, `ingest.py`, `docs/`

**What you actually do in the system:**
You build the **retrieval pipeline** that gives the LLM factual context before it answers. When the worker receives a query like "What do dogs eat?", it calls your retriever to find relevant pet facts from ChromaDB. Without your RAG pipeline, the LLM would answer from its training data only (no guarantee of correctness for the curated pet facts in `docs/`).

**Details of what happens at runtime:**
1. **Offline (ingestion):** `ingest.py` reads all `.txt` and `.md` files from `docs/`, splits text into 500-char chunks with 50-char overlap via `RecursiveCharacterTextSplitter`, embeds each chunk via Ollama's `nomic-embed-text` model, and stores the embeddings + text in ChromaDB at `./chroma_db`.
2. **At query time (called by worker):** `retriever.retrieve(query, top_k=3)`:
   - Check embedding LRU cache (500 entries) → if query embedding is cached, skip Ollama call.
   - Embed the query via `OllamaEmbeddings.embed_query()`.
   - Search ChromaDB's collection for the top 3 most similar chunks by cosine distance.
   - Return `[{content, metadata, distance}]`.
3. `retrieve_with_scores()` returns tuples with similarity scores. `retrieve_batch()` processes multiple queries concurrently.
4. The worker wraps your retrieved docs into a prompt: `"Context: {docs}\n\nQuery: {query}\n\nAnswer:"` and sends it to the LLM. This ensures the answer is grounded in the ingested pet facts.
5. Your `set_base_url()` allows runtime reconfiguration of the Ollama endpoint for the embedder.

---

### 👤 Person 5 — Dashboard + Testing + Client Tools (`dashboard/`, `tests/`, `client/`)

**Files owned:** `dashboard/app.py`, `dashboard/index.html`, `tests/*.py`, `client/load_generator.py`, `client/stress_test.py`

**What you actually do in the system:**
You build three things that validate and monitor everything else:

**Dashboard:** Your FastAPI backend (`dashboard/app.py`) polls the master (`GET /workers`, `GET /metrics`) and the LB (`GET /stats`, `GET /strategy`, `GET /workers`) every 3 seconds and serves a combined `/api/dashboard` endpoint. Your frontend (`index.html`) renders real-time Chart.js graphs. Without the dashboard, there is no way to see routing strategy, worker health, error rates, or latency percentiles in real time — the system is a black box.

**Tests:** Your 117+ pytest tests are the only automated validation of the entire system. They cover:
- LB routing strategies, failover, health checks, pending queue
- RAG retriever initialization, ChromaDB connection, cache behavior
- Worker health, query handling, GPU monitoring, error handling
- Backpressure, graceful degradation, master failure, recovery

**Client Tools:** Your `load_generator.py` is what demonstrates the system working — it sends real queries (drawn from 20 templates) at configurable concurrency with a warmup phase. Your `stress_test.py` escalates through 10→50→100→250→500→1000 concurrent users to find breaking points. Without these tools, there is no way to prove the system handles load.

---

### 👤 Person 6 — System Integration + LLM Engine + Benchmarking + Scripts

**Files owned:** `llm/inference.py`, `main.py`, `benchmark.py`, `scripts/*.ps1`, `requirements.txt`

**What you actually do in the system:**
You build four critical pieces that the other components cannot function without:

**LLM Inference Engine:** Your `InferenceEngine` class in `llm/inference.py` is what every worker imports and calls. When `InferenceEngine.generate_with_context(query, docs)` is called, your code:
1. Constructs the context-augmented prompt from retrieved documents.
2. Acquires the 20-concurrent-call semaphore (prevents Ollama OOM).
3. Sends `POST /api/generate` to Ollama with the prompt, model name, and generation parameters.
4. Returns the generated text. If Ollama is down, the error propagates to the worker → LB retries.
- Without this engine, every worker would need its own Ollama client code — you provide the shared abstraction.

**System Launcher:** Your `main.py` is how everything starts. `python main.py start` launches master (9000), 4 workers (8001-8004), checks for nginx (installed → runs on 8000 / not found → starts Python LB on 8000), LB controller (8005), and dashboard (8100) in the correct order. `main.py stop` kills all processes by PID. Without this, each component must be started manually in the right order.

**Benchmark Suite:** Your `benchmark.py` is the only tool that measures system throughput, latency, and fault tolerance. `run_benchmark_suite()` iterates over model/worker/concurrency/strategy combinations. `run_fault_test()` runs a 6-phase test: baseline → kill a worker → verify LB routes around it → restart worker → verify it rejoins → compare. Without benchmarks, there is no data to prove the system works or to find bottlenecks.

**PowerShell Scripts:** Your `scripts/start_ollama_servers.ps1` launches multiple Ollama instances on different ports (11434, 11435, 11436) so different workers can have dedicated Ollama backends. Your `requirements.txt` pins all dependencies so the project is reproducible.

---

## System Scalability Analysis

### Architecture Scalability

The system uses a **horizontal scaling** model. Each component can scale independently:

| Component | Scaling Strategy | Current Capacity | How to Scale |
|-----------|-----------------|-----------------|--------------|
| **Workers** | Horizontal (add more) | 4 workers (ports 8001-8004) | Start more workers on different ports; add them to LB's upstream |
| **Load Balancer** | Vertical (add NGINX) | 1 LB, 1000 concurrent | Replace custom LB with NGINX (already configured) for production-grade handling; add DNS round-robin across multiple LB instances |
| **Ollama** | Horizontal (multiple instances) | 1 Ollama on port 11434 | Run Ollama instances on multiple ports/GPUs, assign workers to different instances |
| **ChromaDB** | Vertical, single SQLite | 1 connection pool | Switch to ChromaDB client/server mode with dedicated server |
| **Master** | Single point | 1 instance | Stateless design — could be replicated with shared state via Redis |

### Throughput Limits

From actual benchmark data:

| Concurrency | Workers | Throughput | Avg Latency | p95 Latency | Error Rate | Limiting Factor |
|------------|---------|-----------|-------------|-------------|------------|----------------|
| **4** | 4 | 1.64 req/s | 2.44s | 6.06s | 0% | Ollama inference speed |
| **100** | 3 | 2.0 req/s | 32.3s | 49.4s | 0% | Ollama queueing (93% cache hit helped) |

The key insight: **throughput is capped by Ollama's serial inference speed** (~1-2 req/s for smollm2:135m on consumer GPU). Adding workers increases parallelism but **each additional worker still shares the same Ollama instance**, so throughput doesn't scale linearly.

### Bottleneck Hierarchy (outer to inner)

```
Client requests
    ↓
LB Semaphore (1000 max)          ← Soft cap: 503 beyond 1000 concurrent
    ↓
Worker Backpressure (1000/worker) ← Soft cap: 503 beyond queue size
    ↓
Worker Semaphore (250/worker)     ← Soft cap: 250 concurrent tasks per worker
    ↓
LLM Semaphore (20/worker)         ← Queues Ollama calls
    ↓
Ollama Single-Process Inference   ← HARD BOTTLENECK: ~1-2 req/s serial
    ↓
GPU/Memory/VRAM                   ← HARD LIMIT: OOM at ~4-8 concurrent model loads
```

---

## When Does the System Die?

The system dies (or degrades to unusable) at these breaking points:

### 1. Ollama Crash — The Real Killer (Hard Death)

**Trigger:** >4-8 concurrent inference requests hitting Ollama simultaneously
**Mechanism:** Ollama loads the model into GPU VRAM. Each concurrent request either queues (if same model) or loads a new model instance (if different). With `smollm2:135m` using ~800MB VRAM, exceeding GPU memory causes Ollama to crash or hang.
**Symptoms:** Workers return 502/504 errors, benchmark shows 100% failure rate.
**Mitigation:** The 20-concurrent semaphore in `InferenceEngine` helps, but if all 20 burst Ollama simultaneously, it still crashes.
**Death at:** ~50-100 concurrent users sending requests at once (with 4 workers × 250 task slots, all funneling into 1 Ollama with 20 slots).

### 2. LB Semaphore Exhaustion (Soft Death)

**Trigger:** >1000 concurrent requests reaching the LB
**Mechanism:** `MAX_CONCURRENT_REQUESTS = 1000` — the LB's `asyncio.Semaphore` blocks. Beyond 1000 in-flight, requests get `503 Service Unavailable`.
**Symptoms:** Error rate spikes, `reached_max_concurrent` counter increments.
**Kill at:** 1001+ concurrent requests to a single LB instance.
**Mitigation:** Add NGINX with `worker_connections 8192` and multiple LB instances behind DNS.

### 3. Worker Backpressure Rejection (Soft Death)

**Trigger:** >1000 active connections on a single worker
**Mechanism:** `BACKPRESSURE_QUEUE_SIZE = 1000`. The worker checks `if active_connections >= BACKPRESSURE_QUEUE_SIZE` and returns HTTP 503.
**Symptoms:** Workers report 503s, LB reassigns to other workers. If all workers are saturated, LB starts enqueuing to `pending_requests.json`.
**Death at:** 4001+ concurrent requests (4 workers × 1000 + 1).

### 4. Network Socket Exhaustion (Hard Death — Windows)

**Trigger:** Ephemeral port exhaustion on a single machine
**Mechanism:** Windows has ~16,384 ephemeral ports (default range). Each concurrent HTTP connection consumes one. With 1000+ concurrent requests going through LB → Worker → Ollama, each request uses multiple ports. Eventually `WSAENOBUFS` / `Address already in use`.
**Symptoms:** `httpx.ConnectError`, connection refused, random failures across all components.
**Death at:** ~8,000-10,000 concurrent sockets (shared across all components).

### 5. Memory Exhaustion (Hard Death)

**Trigger:** Too many workers + too many concurrent requests
**Mechanism:** Each uvicorn worker process consumes ~100-200MB baseline. 4 workers = 400-800MB. Each in-flight request holds data (prompts, context docs, responses). At 1000 concurrent requests with ~50KB average request size, that's ~50MB additional. But Python's garbage collection and async stack overhead multiply this.
**Symptoms:** System starts swapping to disk → latency spikes to minutes → OOM killer terminates processes.
**Death at:** ~500-1000 concurrent in-flight requests on a system with 8-16GB RAM.

### 6. ChromaDB SQLite Contention (Degradation)

**Trigger:** >10-20 concurrent retrieval requests
**Mechanism:** ChromaDB's default SQLite backend has writer-lock contention. Multiple concurrent writes (rare in read-only mode) or heavy reads cause `database is locked` errors.
**Symptoms:** Retrieval time spikes from ~600ms to >5s, query failures.
**Mitigation:** Not an issue for read-heavy workloads. Switch to ChromaDB client/server for production.

### Summary: System Death Thresholds

| Scenario | Concurrent Users | Throughput | Latency | Behavior |
|----------|-----------------|-----------|---------|----------|
| **Normal** | 1-50 | 1-2 req/s | 1-5s | Full success, healthy |
| **Stressed** | 50-200 | 2-4 req/s | 5-40s | Latency spikes, queue builds, cache helps |
| **Degraded** | 200-500 | 4-6 req/s | 40-120s | Heavy queuing, requests time out (>60s) |
| **Near Death** | 500-1000 | 6-8 req/s | 120-300s | Mass timeouts, LB semaphore approaching limit |
| **🟢 Alive** | 0-1000 | Varies | Varies | Returns results eventually — **graceful degradation** |
| **💀 Dead** | >1000 concurrent at LB | N/A | N/A | 503 Service Unavailable |
| **💀 Dead** | Ollama OOM | N/A | N/A | Crash, all workers return errors |
| **💀 Dead** | Ephemeral port exhaustion | N/A | N/A | All TCP connections fail |

### Key Takeaway

**The system is designed to degrade gracefully, not die.** Under load it:
1. 🟢 Caches help (93% hit rate at 100 concurrency)
2. 🟡 Backpressure rejects excess (503) instead of crashing
3. 🟠 Pending queue persists failed requests for retry
4. 🔴 All resources exhausted → components crash individually, but the LB keeps retrying survivors

The **hardest bottleneck is Ollama** — it's inherently serial for inference. The system is CPU/network scalable, but **GPU inference is the fundamental floor** on throughput. To handle 1000+ concurrent users with sub-5s latency, you would need **multiple Ollama instances across multiple GPUs** (one per worker), not one Ollama shared by all workers.
