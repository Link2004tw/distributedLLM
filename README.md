# Distributed LLM Inference System with RAG and Load Balancing

Distributed system for handling 1000+ concurrent LLM requests with RAG, load balancing, and fault tolerance.

## Architecture

```
Client (benchmark.py)
  ↓ HTTP POST /query
NGINX (port 8000) — round_robin / least_connections
  ↓
Workers (ports 8001-8004) — FastAPI + Ollama LLM
  ↓
ChromaDB (vector store) ← Ollama embeddings
Master (port 9000) — heartbeat monitoring, /schedule endpoint
```

## Quick Start (Google Colab)

### Cell 1 — Install Ollama + pull models
```python
!curl -fsSL https://ollama.com/install.sh | sh
import subprocess, time
subprocess.Popen(["ollama", "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(3)
!ollama pull smollm2:135m
!ollama pull nomic-embed-text
```

### Cell 2 — Install Python deps + clone
```python
!pip install -q fastapi uvicorn pydantic httpx langchain langchain-ollama langchain-chroma chromadb
!git clone <your-repo-url> distributedLLM
%cd distributedLLM
```

### Cell 3 — Ingest RAG documents
```python
!python ingest.py
```

### Cell 4 — Run benchmark
```python
# Quick test (low concurrency)
!python benchmark.py --single --workers 4 --concurrency 20 --requests 200

# High concurrency (takes longer, timeout=3600s)
!python benchmark.py --single --workers 4 --concurrency 1000 --requests 1000
```

### Cell 5 — Fault tolerance test
```python
!python benchmark.py --fault-test --workers 4 --concurrency 20 --requests 200
```

## Running Tests

Start services first, then run pytest:

```bash
# Terminal 1: Start master
uvicorn master.monitor:app --port 9000

# Terminal 2-5: Start workers
uvicorn workers.worker:app --port 8001
uvicorn workers.worker:app --port 8002
uvicorn workers.worker:app --port 8003
uvicorn workers.worker:app --port 8004

# Terminal 6: Start NGINX
cp lb/nginx.conf /etc/nginx/nginx.conf && nginx

# Terminal 7: Run tests
pytest tests/ -v
```

Or run a single test file:
```bash
pytest tests/test_load_balancer.py -v
pytest tests/test_rag.py -v -k "test_basic_retrieval"
```

## CLI Reference

```bash
python benchmark.py --single --workers 4 --concurrency 100 --requests 500
python benchmark.py --fault-test --workers 4 --concurrency 20 --requests 200
python main.py master                        # Start master only
python main.py worker 1                      # Start worker-1
python main.py controller                    # Start LB controller
python ingest.py                             # Ingest RAG documents
```

## Project Files — Complete Reference

### Core System (used by benchmark)

| File | What benchmark.py does with it | Role |
|---|---|---|
| `benchmark.py` | Entry point — runs the test | Benchmark suite: starts components, runs load test, RAG accuracy, fault injection |
| `master/monitor.py` | Starts as subprocess on port 9000 | Master node: worker registration, heartbeat monitoring (5s), `/schedule` endpoint |
| `workers/worker.py` | Starts as subprocess on ports 8001-8004 | Worker: FastAPI app with RAG + LLM pipeline, response caching, GPU stats |
| `llm/inference.py` | Imported by worker.py | Async InferenceEngine: calls Ollama `/api/generate` via httpx, semaphore-limited (20) |
| `rag/retriever.py` | Imported by worker.py | ChromaDB retriever: similarity search, batch retrieval, embedding cache |
| `common/models.py` | Imported by master/monitor.py | Shared dataclasses: WorkerInfo, HealthCheck, MetricsSummary |
| `lb/nginx.conf` | Copied to /etc/nginx/nginx.conf | NGINX configuration: 8192 connections, proxy_next_upstream retry, 3600s timeout |

### Load Balancer & Controller

| File | Usage | Role |
|---|---|---|
| `lb/load_balancer.py` | Run via `python -m uvicorn lb.load_balancer:app` or `main.py lb` | 5 routing strategies, health checks, pending request persistence, master scheduling coordination |
| `lb/app.py` | Run via `main.py controller`, imports from `lb/load_balancer.py` | LB Controller: worker enable/disable, strategy switching, status endpoints |

### Document Ingestion

| File | Usage | Role |
|---|---|---|
| `ingest.py` | Run directly: `python ingest.py` | Reads `docs/*.txt`, splits into chunks, embeds with nomic-embed-text, stores in ChromaDB |
| `docs/dog_facts.txt` | Read by ingest.py | Source document for RAG (pet facts about dogs) |
| `docs/cat_facts.txt` | Read by ingest.py | Source document for RAG (pet facts about cats) |
| `docs/hamster_facts.txt` | Read by ingest.py | Source document for RAG (pet facts about hamsters) |
| `docs/bird_facts.txt` | Read by ingest.py | Source document for RAG (pet facts about birds) |
| `docs/fish_facts.txt` | Read by ingest.py | Source document for RAG (pet facts about fish) |
| `docs/rabbit_facts.txt` | Read by ingest.py | Source document for RAG (pet facts about rabbits) |
| `docs/turtle_facts.txt` | Read by ingest.py | Source document for RAG (pet facts about turtles) |

### Client Load Test Tools

| File | Usage | Role |
|---|---|---|
| `client/load_generator.py` | Imported by tests/test_load_balancer.py and client/stress_test.py | LoadTestRunner: configurable concurrent request simulation with warmup and reporting |
| `client/stress_test.py` | Imported by tests/test_load_balancer.py | Multi-level stress test runner: iterates concurrency 10→50→100→250→500→1000 |

### Launcher

| File | Usage | Role |
|---|---|---|
| `main.py` | Run directly: `python main.py start|master|worker|lb|controller` | Launcher: `start` boots everything, individual commands for single components |

### Test Suite (pytest)

| File | What it tests |
|---|---|
| `tests/conftest.py` | Pytest fixtures: lb_url, master_url, worker_url, verify_services, sample_query |
| `tests/test_load_balancer.py` | 25+ tests: health endpoints, routing strategies (rr/least/hybrid/gpu-aware), query handling, worker management, fault tolerance, batch, streaming |
| `tests/test_rag.py` | 283 lines: retriever init, ChromaDB connection, retrieval quality, embedding consistency, specific queries (dog/cat/hamster), cache |
| `tests/test_ollama.py` | 206 lines: model availability, generate/embedding endpoints, GPU detection, inference latency |
| `tests/test_critical_fixes.py` | 366 lines: backpressure semaphore, worker auto-discovery, graceful degradation, feature parity |
| `tests/test_gpu_worker.py` | 305 lines: health endpoints, query endpoints, GPU monitoring, caching, error handling |
| `tests/test_failure_simulation.py` | 303 lines standalone (run directly): failure detection, LB routing with failed workers, restart recovery |

### Configuration

| File | Role |
|---|---|
| `requirements.txt` | Python dependencies: fastapi, uvicorn, httpx, langchain-ollama, langchain-chroma, chromadb |
| `pytest.ini` | Pytest config: test discovery pattern (`test_*.py`), markers (health, query, gpu, load, cache, slow, fault_tolerance), 120s timeout |

### Data Files (auto-generated)

| File | Generated by | Role |
|---|---|---|
| `benchmark_result_latest.json` | `benchmark.py --single` | Latest benchmark results: success rate, throughput, latency percentiles, RAG accuracy |
| `load_test_results.json` | `client/stress_test.py` | Multi-level load test results across concurrency levels |

### PowerShell Scripts (Windows utilities)

| File | Role |
|---|---|
| `start.ps1` | Start all system components (master, 4 workers, NGINX) on Windows |
| `restart-all.ps1` | Kill and restart all components |
| `load-test.ps1` | Run load test with configurable parameters |
| `scripts/start_workers.ps1` | Start worker processes |
| `scripts/start_ollama_servers.ps1` | Start multiple Ollama instances |
| `scripts/stop_ollama_servers.ps1` | Stop Ollama instances |

### HTTP Request Files (development)

| File | Role |
|---|---|
| `requests/env.http` | VS Code REST Client environment variables |
| `requests/master_requests.http` | Test Master endpoints (register, workers, metrics) |
| `requests/worker_requests.http` | Test Worker endpoints (query, health, gpu-stats) |
| `requests/lb_requests.http` | Test LB endpoints (strategy, workers, stats) |
| `requests/quickstart.http` | Quick smoke test requests |
| `requests/load_test.http` | Load test requests |
| `requests/test_all.http` | Comprehensive endpoint test suite |


### Data Directories (auto-generated)

| Directory | Created by | Content |
|---|---|---|
| `chroma_db/` | `ingest.py` | ChromaDB vector store: embedded document chunks for RAG retrieval |
| `chroma_db/chroma.sqlite3` | `ingest.py` | SQLite database backing ChromaDB (auto-generated, in `.gitignore`) |

### Package Markers (empty)

| File | Role |
|---|---|
| `llm/__init__.py` | Marks `llm/` as Python package |
| `rag/__init__.py` | Marks `rag/` as Python package |
| `tests/__init__.py` | Marks `tests/` as Python package |