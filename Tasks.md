# Project Tasks

## Legend
- **Priority**: 🔴 Critical — 🟠 High — 🟡 Medium — 🟢 Low
- **Difficulty**: ⭐ Easy — ⭐⭐ Medium — ⭐⭐⭐ Hard

---

## Phase 1 — Architecture & Setup

| # | Task | Description | Module | Priority | Difficulty |
|---|------|-------------|--------|----------|------------|
| 1.1 | Define project folder structure | Create all folders and empty `__init__.py` files as defined in STACK.md | All | 🔴 Critical | ⭐ |
| 1.2 | Define `Request` and `Response` dataclasses | Create `common/models.py` with shared data models used across all components | `common` | 🔴 Critical | ⭐ |
| 1.3 | Install and verify all dependencies | Run pip installs, verify Ollama is running, pull LLM model, confirm ChromaDB initializes | All | 🔴 Critical | ⭐ |
| 1.4 | Pull and test LLM via Ollama | Run `ollama pull smollm2`, send a test prompt, confirm response | `llm` | 🔴 Critical | ⭐ |
| 1.5 | Design system architecture diagram | Draw component diagram showing all nodes, ports, and data flow | Documentation | 🟠 High | ⭐ |

---

## Phase 2 — Core Implementation

| # | Task | Description | Module | Priority | Difficulty |
|---|------|-------------|--------|----------|------------|
| 2.1 | Implement LLM inference module | Create `llm/inference.py` using LangChain's `OllamaLLM` to send prompts and return responses | `llm` | 🔴 Critical | ⭐⭐ |
| 2.2 | Implement document ingestion script | Write `ingest.py` to read source documents, chunk them, embed with BGE-M3, and store in ChromaDB | `rag` | 🔴 Critical | ⭐⭐ |
| 2.3 | Implement RAG retriever | Create `rag/retriever.py` to embed an incoming query and retrieve top-K relevant chunks from ChromaDB | `rag` | 🔴 Critical | ⭐⭐ |
| 2.4 | Implement GPU Worker Node | Create `workers/worker.py` as a FastAPI app that runs the full RAG + LLM pipeline per request and returns latency metadata | `workers` | 🔴 Critical | ⭐⭐⭐ |
| 2.5 | Implement Round Robin load balancer | Create `lb/load_balancer.py` as a FastAPI app with thread-safe round robin routing across registered workers | `lb` | 🔴 Critical | ⭐⭐ |
| 2.6 | Wire up basic end-to-end flow | Manually test: client sends request → load balancer → worker → RAG → LLM → response returned correctly | All | 🔴 Critical | ⭐⭐ |

---

## Phase 3 — Load Balancing Strategies

| # | Task | Description | Module | Priority | Difficulty |
|---|------|-------------|--------|----------|------------|
| 3.1 | Implement Least Connections strategy | Track active request count per worker; route new requests to the worker with the lowest count | `lb` | 🟠 High | ⭐⭐ |
| 3.2 | Implement Load-Aware Routing strategy | Extend least connections with a health score based on recent average latency per worker | `lb` | 🟡 Medium | ⭐⭐⭐ |
| 3.3 | Make routing strategy configurable | Allow switching between Round Robin, Least Connections, and Load-Aware via a config variable or environment variable | `lb` | 🟡 Medium | ⭐ |

---

## Phase 4 — Master Node & Fault Tolerance

| # | Task | Description | Module | Priority | Difficulty |
|---|------|-------------|--------|----------|------------|
| 4.1 | Implement Master Node heartbeat monitor | Create `master/monitor.py` as a FastAPI app that pings each worker every 5 seconds and tracks health status | `master` | 🔴 Critical | ⭐⭐⭐ |
| 4.2 | Implement worker failure detection | Declare a worker failed after 3 consecutive missed heartbeats; log the failure event with timestamp | `master` | 🔴 Critical | ⭐⭐ |
| 4.3 | Implement automatic worker removal from routing pool | When Master Node marks a worker as failed, it notifies the Load Balancer to remove that worker from the active pool | `master` / `lb` | 🔴 Critical | ⭐⭐ |
| 4.4 | Implement task reassignment on worker failure | Track in-flight requests per worker; requeue them to healthy workers when a failure is detected | `master` / `lb` | 🟠 High | ⭐⭐⭐ |
| 4.5 | Implement worker self-registration | Each worker registers itself with the Master Node on startup and deregisters on graceful shutdown | `workers` / `master` | 🟠 High | ⭐⭐ |
| 4.6 | Test fault tolerance by killing a worker mid-run | Run load test with 4 workers, kill one process manually, verify no requests are lost and system continues | Testing | 🔴 Critical | ⭐⭐ |

---

## Phase 5 — Testing & Evaluation

| # | Task | Description | Module | Priority | Difficulty |
|---|------|-------------|--------|----------|------------|
| 5.1 | Implement 1000-user load generator | Create `client/load_generator.py` using Python threading to simulate 1000 concurrent users and collect latency stats | `client` | 🔴 Critical | ⭐⭐ |
| 5.2 | Run load tests at increasing concurrency | Test at 100, 250, 500, and 1000 concurrent users; record average latency and throughput at each level | Testing | 🟠 High | ⭐ |
| 5.3 | Compare load balancing strategies | Run the same load test with Round Robin vs Least Connections vs Load-Aware; compare latency and distribution fairness | Testing | 🟠 High | ⭐⭐ |
| 5.4 | Measure per-worker GPU/CPU utilization | Monitor resource usage during load tests using `psutil` or system tools; include in report | Testing | 🟡 Medium | ⭐⭐ |
| 5.5 | Run failure simulation test | Kill 1–2 workers during a live load test; verify failure detection time, reassignment correctness, and zero dropped requests | Testing | 🔴 Critical | ⭐⭐ |

---

## Phase 6 — Documentation & Delivery

| # | Task | Description | Module | Priority | Difficulty |
|---|------|-------------|--------|----------|------------|
| 6.1 | Write project report | Cover problem definition, system design, implementation details, testing results, limitations, and references using the instructor's template | Documentation | 🔴 Critical | ⭐⭐ |
| 6.2 | Record YouTube demo video | Demonstrate the system running live: start all components, run the load test, show logs, simulate a worker failure, show recovery | Documentation | 🔴 Critical | ⭐ |
| 6.3 | Prepare presentation slides | Summarize architecture, key design decisions, results, and lessons learned | Documentation | 🔴 Critical | ⭐ |
| 6.4 | Clean up and comment codebase | Add docstrings to all modules, remove debug prints, ensure the project runs from a clean install following STACK.md | All | 🟠 High | ⭐ |
