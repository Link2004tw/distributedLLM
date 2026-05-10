# Distributed LLM Inference System with RAG and Load Balancing

A Python-based distributed computing system designed to handle **1000+ concurrent user requests** for Large Language Model (LLM) inference augmented with **Retrieval-Augmented Generation (RAG)**. The system runs locally on a single machine using process-level isolation — each component is an independent OS process with its own HTTP server.

---

## Architecture

The system is organized into **five distinct layers**, each running as an independent component:

| Layer             | Port      | Technology                  | Purpose                                                                       |
| ----------------- | --------- | --------------------------- | ----------------------------------------------------------------------------- |
| **Client**        | —         | `threading`                 | Simulates 1000+ concurrent users, measures per-request latency and throughput |
| **Load Balancer** | 8000      | FastAPI                     | Single entry point with 3 routing strategies                                  |
| **Master Node**   | 9000      | FastAPI                     | Health monitor, failure detection, metrics dashboard, task reassignment       |
| **GPU Workers**   | 8001–8004 | FastAPI (x4)                | Independent processes running the full RAG + LLM pipeline                     |
| **RAG Pipeline**  | —         | ChromaDB + nomic-embed-text | Offline document indexing + online semantic retrieval                         |

### System Architecture

```
User (thread)
  → HTTP POST /query  →  Load Balancer (port 8000)
                               ↓  selects worker (routing strategy)
Worker Node (port 800X)
                                ↓  embed query (nomic-embed-text)
                           ChromaDB  →  top-K chunks
                               ↓  build augmented prompt
                          Ollama (LLM)  →  generated answer
                               ↓  return response + latency
   ← HTTP 200 JSON  ←  Load Balancer  ←  Worker Node
```

---

## Technology Stack

| Category              | Tool                               | Notes                                                           |
| --------------------- | ---------------------------------- | --------------------------------------------------------------- |
| **Language**          | Python 3.10+                       | All components                                                  |
| **LLM Runtime**       | Ollama                             | Serves models via HTTP API                                      |
| **LLM Models**        | SmolLM2, Qwen2.5 3B, Mistral 7B    | Via LangChain `OllamaLLM`                                       |
| **Embeddings**        | nomic-embed-text                   | LangChain + Ollama                                              |
| **Vector DB**         | ChromaDB                           | On-disk, shared across all workers                              |
| **Web Framework**     | FastAPI + Uvicorn                  | Each component runs as a separate process                       |
| **RAG Orchestration** | LangChain ecosystem                | `langchain-ollama`, `langchain-chroma`, `langchain-huggingface` |
| **Load Testing**      | `threading`, `time`, `collections` | 1000 concurrent user simulation                                 |

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

**Install Ollama (Windows PowerShell):**

```powershell
irm https://ollama.com/install.ps1 | iex
```

**Install Ollama (macOS/Linux):**

```bash
curl -fsSL https://ollama.com/install.sh | sh
```

### 1. Create Virtual Environment (Recommended)

```bash
python -m venv .venv
```

Activate the environment:

**Windows (PowerShell):**

```powershell
.venv\Scripts\Activate
```

**Windows (CMD):**

```cmd
.venv\Scripts\activate.bat
```

**Linux/Mac:**

```bash
source .venv/bin/activate
```

### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

### 3. Pull Ollama Models

```bash
ollama pull nomic-embed-text
ollama pull smollm2
```

### 4. Ingest Documents

```bash
python ingest.py
```

This reads source documents, splits them into chunks, embeds with nomic-embed-text, and stores vectors in ChromaDB on disk.

### 5. Start System Components

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

### 6. Run Load Test

```bash
python client/load_generator.py
```

### 6. Test RAG Pipeline (Optional)

```bash
python rag/test_retriever.py
```

---

## RAG Pipeline Setup

### Running ingest.py

```bash
python ingest.py
```

This script:

1. Reads all `.txt` and `.md` files from the `docs/` folder
2. Splits documents into chunks (500 chars, 50 overlap)
3. Embeds chunks using the configured embedding model
4. Stores vectors in ChromaDB at `./chroma_db`

### Adding New Documents

1. Add `.txt` or `.md` files to the `docs/` folder
2. Delete existing database:
   ```powershell
   Remove-Item -Recurse -Force .\chroma_db
   ```
3. Re-run ingest:
   ```bash
   python ingest.py
   ```

### Configuration (ingest.py)

| Variable          | Default                   | Description              |
| ----------------- | ------------------------- | ------------------------ |
| `EMBEDDING_MODEL` | `nomic-embed-text:latest` | Ollama embedding model   |
| `CHROMA_DB_PATH`  | `./chroma_db`             | Vector database location |
| `DOCS_PATH`       | `./docs`                  | Source documents folder  |
| `chunk_size`      | 500                       | Characters per chunk     |
| `chunk_overlap`   | 50                        | Overlap between chunks   |

---

## Load Balancing Strategies

| Strategy              | Description                                                                     |
| --------------------- | ------------------------------------------------------------------------------- |
| **Round Robin**       | Distributes requests evenly across all active workers in sequence               |
| **Least Connections** | Routes each request to the worker currently handling the fewest active requests |
| **Load-Aware**        | Extends least connections with worker health scoring based on recent latency    |

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

---

## Troubleshooting

### "model not found" error

```bash
# Pull the required Ollama models
ollama pull nomic-embed-text
ollama pull smollm2:135m
```

### ChromaDB not found / empty results

```powershell
# Delete and rebuild the vector database
Remove-Item -Recurse -Force .\chroma_db
python ingest.py
```

### Ollama not running

```bash
# Start Ollama service
ollama serve
```

### Connection refused (port already in use)

```powershell
# Find and kill process on port
netstat -ano | findstr :8000
taskkill /PID <PID> /F
```

### Import errors (ModuleNotFoundError)

```powershell
# Ensure you're in project root
cd E:\coding\python\distributed
# Or set PYTHONPATH
$env:PYTHONPATH = "E:\coding\python\distributed"
```

### Slow retrieval / high latency

- Check embedding model is loaded in Ollama: `ollama list`
- Reduce `top_k` in requests
- Consider using a lighter embedding model
