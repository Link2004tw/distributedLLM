# Technology Stack

## Runtime & Language

| Tool | Version | Role |
|------|---------|------|
| Python | 3.10+ | Primary language for all components |
| Ollama | Latest | Local LLM runtime — serves the model as an HTTP API |

---

## LLM

| Tool | Notes |
|------|-------|
| **SmolLM2** (default) | Very lightweight, fast inference, suitable for high concurrency simulation |
| **Qwen2.5 3B** (recommended) | Significantly stronger instruction following at similar resource cost |
| **Mistral 7B** (optional) | Best quality, requires more RAM (~8GB) |

All models are pulled and served via Ollama. LangChain's `OllamaLLM` class is used to call them from Python.

---

## Embeddings

| Tool | Notes |
|------|-------|
| **BGE-M3** (`BAAI/bge-m3`) | Primary embedding model — multilingual, long-context, high quality |
| **nomic-embed-text** (alternative) | Runs through Ollama, no extra library needed, faster but lower quality |

BGE-M3 is loaded via `sentence-transformers` and wrapped with LangChain's `HuggingFaceEmbeddings`.

---

## Vector Database

| Tool | Notes |
|------|-------|
| **ChromaDB** | Stores and retrieves document embeddings for RAG. Runs fully locally, persists to disk, Python-native. Chosen for simplicity and zero-setup. |

ChromaDB is initialized once during document ingestion and shared across all worker nodes at runtime via a shared on-disk path.

---

## Web Framework

| Tool | Role |
|------|------|
| **FastAPI** | HTTP server for Load Balancer, Master Node, and all Worker Nodes |
| **Uvicorn** | ASGI server that runs each FastAPI app as its own process |

Each system component is a separate FastAPI app running on a dedicated port. This is what makes the system genuinely process-distributed rather than just thread-distributed.

---

## RAG Orchestration

| Tool | Notes |
|------|-------|
| **LangChain** | Wires together the retrieval and LLM steps into a clean pipeline |
| **langchain-ollama** | LangChain integration for Ollama LLM and embeddings |
| **langchain-chroma** | LangChain integration for ChromaDB retriever |
| **langchain-huggingface** | LangChain integration for HuggingFace embedding models |

---

## Load Testing & Metrics

| Tool | Role |
|------|------|
| **threading** (stdlib) | Spawns 1000 concurrent user threads for load testing |
| **time** (stdlib) | Per-request latency measurement |
| **collections** (stdlib) | Aggregating throughput and latency statistics |

---

## Installation

```bash
# 1. Install Ollama and pull models
ollama pull smollm2
ollama pull nomic-embed-text   # optional

# 2. Install Python dependencies
pip install fastapi uvicorn
pip install langchain langchain-ollama langchain-chroma langchain-huggingface
pip install chromadb
pip install sentence-transformers   # for BGE-M3

# 3. Ingest documents into ChromaDB (run once)
python ingest.py

# 4. Start system components (each in its own terminal)
uvicorn master.monitor:app --port 9000
uvicorn workers.worker:app --port 8001
uvicorn workers.worker:app --port 8002
uvicorn workers.worker:app --port 8003
uvicorn workers.worker:app --port 8004
uvicorn lb.load_balancer:app --port 8000

# 5. Run load test
python client/load_generator.py
```

---

## Project Folder Structure

```
project/
├── common/
│   └── models.py          # Request / Response dataclasses
├── lb/
│   └── load_balancer.py   # FastAPI load balancer (port 8000)
├── master/
│   └── monitor.py         # Master node health monitor (port 9000)
├── workers/
│   └── worker.py          # GPU worker node (ports 8001–8004)
├── rag/
│   └── retriever.py       # ChromaDB retrieval logic
├── llm/
│   └── inference.py       # Ollama LLM call via LangChain
├── client/
│   └── load_generator.py  # 1000-user load test
├── ingest.py              # One-time document ingestion script
└── main.py                # Convenience launcher (optional)
```
