# Distributed LLM Inference System with RAG and Load Balancing

A Python-based distributed computing system designed to handle **1000+ concurrent user requests** for Large Language Model (LLM) inference augmented with **Retrieval-Augmented Generation (RAG)**. The system runs locally on a single machine using process-level isolation — each component is an independent OS process with its own HTTP server.

---

## Architecture

The system is organized into **five distinct layers**, each running as an independent component:

| Layer | Port | Technology | Purpose |
|-------|------|------------|---------|
| **Client** | — | `threading` | Simulates 1000+ concurrent users, measures per-request latency and throughput |
| **Load Balancer** | 8000 | FastAPI | Single entry point with 3 routing strategies |
| **Master Node** | 9000 | FastAPI | Health monitor, failure detection, metrics dashboard, task reassignment |
| **GPU Workers** | 8001–8004 | FastAPI (x4) | Independent processes running the full RAG + LLM pipeline |
| **RAG Pipeline** | — | ChromaDB + BGE-M3 | Offline document indexing + online semantic retrieval |

### System Architecture

```
User (thread)
  → HTTP POST /query  →  Load Balancer (port 8000)
                               ↓  selects worker (routing strategy)
                          Worker Node (port 800X)
                               ↓  embed query (BGE-M3)
                          ChromaDB  →  top-K chunks
                               ↓  build augmented prompt
                          Ollama (LLM)  →  generated answer
                               ↓  return response + latency
   ← HTTP 200 JSON  ←  Load Balancer  ←  Worker Node
```

---

## Technology Stack

| Category | Tool | Notes |
|----------|------|-------|
| **Language** | Python 3.10+ | All components |
| **LLM Runtime** | Ollama | Serves models via HTTP API |
| **LLM Models** | SmolLM2, Qwen2.5 3B, Mistral 7B | Via LangChain `OllamaLLM` |
| **Embeddings** | BGE-M3 (primary), nomic-embed-text (alt) | `sentence-transformers` + LangChain |
| **Vector DB** | ChromaDB | On-disk, shared across all workers |
| **Web Framework** | FastAPI + Uvicorn | Each component runs as a separate process |
| **RAG Orchestration** | LangChain ecosystem | `langchain-ollama`, `langchain-chroma`, `langchain-huggingface` |
| **Load Testing** | `threading`, `time`, `collections` | 1000 concurrent user simulation |

---

## Project Structure

```
project/
├── common/
│   └── models.py            # Shared Request/Response dataclasses
├── lb/
│   └── load_balancer.py     # Load balancer with 3 routing strategies (port 8000)
├── master/
│   └── monitor.py           # Health monitor & orchestrator (port 9000)
├── workers/
│   └── worker.py            # GPU worker node template (ports 8001–8004)
├── rag/
│   └── retriever.py         # ChromaDB query embedding & retrieval
├── llm/
│   └── inference.py         # Ollama LLM inference via LangChain
├── client/
│   └── load_generator.py    # 1000-user concurrent load test
├── ingest.py                # One-time document ingestion script
└── main.py                  # Optional convenience launcher
```

---

## Quick Start

### Prerequisites

- **Python 3.10+**
- **Ollama** installed and running

### 1. Install Ollama & Pull Models

```bash
ollama pull smollm2          # default model (lightweight, fast)
ollama pull nomic-embed-text # optional embedding model
```

### 2. Install Python Dependencies

```bash
pip install fastapi uvicorn
pip install langchain langchain-ollama langchain-chroma langchain-huggingface
pip install chromadb
pip install sentence-transformers   # for BGE-M3 embeddings
```

### 3. Ingest Documents (Run Once)

```bash
python ingest.py
```

This reads source documents, splits them into chunks, embeds with BGE-M3, and stores vectors in ChromaDB on disk.

### 4. Start System Components

Each component must run in its own terminal:

```bash
# Master Node (health monitor)
uvicorn master.monitor:app --port 9000

# Worker Nodes (start 4 instances)
uvicorn workers.worker:app --port 8001
uvicorn workers.worker:app --port 8002
uvicorn workers.worker:app --port 8003
uvicorn workers.worker:app --port 8004

# Load Balancer (entry point)
uvicorn lb.load_balancer:app --port 8000
```

### 5. Run Load Test

```bash
python client/load_generator.py
```

---

## Load Balancing Strategies

| Strategy | Description |
|----------|-------------|
| **Round Robin** | Distributes requests evenly across all active workers in sequence |
| **Least Connections** | Routes each request to the worker currently handling the fewest active requests |
| **Load-Aware** | Extends least connections with worker health scoring based on recent latency |

The routing strategy is configurable via environment variable or config setting.

---

## Fault Tolerance

The system implements three mechanisms for resilience:

1. **Heartbeat-based failure detection** — Master Node pings each worker every 5 seconds; 3 consecutive missed heartbeats marks a worker as failed
2. **Automatic task reassignment** — In-flight requests on a failed worker are requeued and redistributed to healthy workers
3. **Load Balancer resilience** — The routing pool updates in real-time; the LB never routes to a worker declared unhealthy by the Master Node

---

## Scope and Limitations

- All components run on a **single physical machine**; "distributed" is simulated at the process level
- Ollama serializes LLM inference internally per instance; true GPU parallelism requires multiple physical GPUs
- ChromaDB is shared across workers via a single on-disk database; production would use a dedicated vector DB server
- Request logs are not persisted across restarts
