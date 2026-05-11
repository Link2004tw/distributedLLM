# Project Task List

## Status Legend
- [x] Completed
- [ ] Pending
- [ ] In Progress

---

## Tasks

### High Priority
1. [x] True Concurrent Request Handling - Semaphore-based backpressure in both LB and worker
2. [x] Automatic Task Reassignment - LB retry logic + Master health detection
3. [x] Worker Auto-Registration - Master notifies LB when workers register
4. [ ] 1000+ Concurrent Users Testing - Full stress test from 100 to 1000 users

### Medium Priority
5. [x] Graceful Degradation - Fallback response when Ollama fails (worker.py)
6. [x] Batch Processing Optimization - True batch grouping before LLM call with embedding batch API
7. [ ] Comprehensive Metrics - P95/P99 latency, detailed throughput, dashboard integration

### Low Priority
8. [ ] Response Streaming - Stream LLM responses to client via SSE
9. [ ] Task Queue Persistence - Persist queue to disk for crash recovery

### Already Completed
- [x] Load Balancing (Round Robin, Least Connections, Hybrid, GPU-aware)
- [x] Worker Nodes (LangChain-based with all endpoints: /gpu-stats, /capabilities, /batch, /ready, /fallback, /health)
- [x] LLM Inference (Ollama + LangChain)
- [x] RAG Integration (ChromaDB + Retriever)
- [x] Health Checks & Failure Detection (Master heartbeats + LB notification)
- [x] Dashboard (FastAPI + Jinja2)
- [x] Master/Scheduler (worker registration + health monitoring)
- [x] Worker Warmup on Startup
- [x] Thread-safe concurrency (asyncio locks on active_connections + latencies)

---

## What's Left (Priority Order)

### 1. Batch Processing Optimization (Medium)
- `/query/batch` currently just fires `asyncio.gather()` on all queries individually
- Should group queries by similar characteristics and batch to Ollama
- Ollama has a `/api/generate` that can be called once per batch with combined prompt

### 2. 1000+ Concurrent Users Testing (High)
- Full stress test: 100 → 500 → 1000 users
- Measure latency, throughput, error rate
- Identify bottlenecks

### 3. Comprehensive Metrics (Medium)
- P95/P99 latency in LB stats
- Dashboard real-time metrics
- Per-worker throughput tracking

### 4. Response Streaming (Low)
- SSE endpoint for streaming LLM tokens
- Chain streaming with RAG retrieval first

### 5. Task Queue Persistence (Low)
- Persist pending requests to disk
- Recovery on crash/restart