# Project Files Documentation

This file documents the purpose of each file and directory in the distributed LLM inference system.

---

## `common/models.py`

Contains shared dataclasses and enumerations used across all system components:

- `QueryRequest` — Input schema for query endpoints
- `QueryResponse` — Output schema with answer, sources, and latency
- `WorkerInfo` — Worker node metadata (id, port, health, connections)
- `RoutingStrategy` — Enum for load balancing strategies (round_robin, least_connections, load_aware)
- `HealthCheck`, `MetricsSummary`, `RequeueRequest` — System message types

---

## `lb/load_balancer.py`

FastAPI application running on port 8000. Acts as the single entry point for all client requests. Implements three routing strategies (round robin, least connections, load-aware) and maintains a live registry of healthy worker nodes. Communicates with the Master Node to stay updated on worker health status.

---

## `master/monitor.py`

FastAPI application running on port 9000. The system's health monitor and orchestrator. Runs a background heartbeat monitor that periodically pings each registered worker. Marks workers as unhealthy if they miss 3 consecutive heartbeats, notifies the Load Balancer to stop routing to failed workers, and exposes a `/metrics` endpoint for real-time system performance data.

---

## `workers/worker.py`

FastAPI application for GPU worker nodes (typically ports 8001–8004). Each worker:

1. Registers itself with the Master Node on startup
2. Embeds incoming queries using BGE-M3 via the Retriever
3. Retrieves top-K relevant documents from ChromaDB
4. Constructs a context-augmented prompt and sends it to Ollama
5. Returns the LLM response with latency metadata

Workers use a thread pool executor for blocking LLM calls while handling async HTTP requests.

---

## `rag/retriever.py`

Shared RAG retrieval logic. Wraps ChromaDB and HuggingFace embeddings (BGE-M3). Provides `retrieve()` method to fetch the top-K most semantically similar document chunks for a given query. Used by all worker nodes at inference time.

---

## `llm/inference.py`

Shared LLM inference logic using LangChain's Ollama integration. Provides `generate_with_context()` method that builds a context-augmented prompt from retrieved documents and the user's query, then invokes the Ollama LLM. Used by all worker nodes.

---

## `client/load_generator.py`

Load testing client that simulates 1000+ concurrent users using Python's threading module. Each thread sends an HTTP POST request to the Load Balancer. Measures per-request latency and aggregates throughput, P50/P95/P99 latency percentiles, and error counts after the test completes.

---

## `ingest.py`

One-time script for document ingestion. Loads source documents from the `./docs` directory (or uses default sample text), splits them into chunks using LangChain's `RecursiveCharacterTextSplitter`, embeds each chunk with BGE-M3, and stores the vectors in ChromaDB on disk. Run once before starting the system.

---

## `main.py`

Convenience launcher script. Provides CLI commands to start individual components:

- `python main.py master` — Start Master Node (port 9000)
- `python main.py worker <n>` — Start Worker n (e.g., port 8001+)
- `python main.py lb` — Start Load Balancer (port 8000)

Alternatively, each component can be started manually with uvicorn.

---

## `docs/`

Directory containing source documents to be ingested into ChromaDB. Place `.txt` or `.md` files here before running `ingest.py`. (Not created by default — add manually as needed.)

---

## `chroma_db/`

Directory where ChromaDB persists vector embeddings. Created automatically when running `ingest.py`. Should be included in `.gitignore` to avoid committing large binary data.

---

## Folder Structure Summary

```
project/
├── common/
│   └── models.py          # Shared dataclasses
├── lb/
│   └── load_balancer.py   # FastAPI load balancer (port 8000)
├── master/
│   └── monitor.py        # Master node health monitor (port 9000)
├── workers/
│   └── worker.py        # GPU worker node (ports 8001–8004)
├── rag/
│   └── retriever.py    # ChromaDB retrieval logic
├── llm/
│   └── inference.py     # Ollama LLM call via LangChain
├── client/
│   └── load_generator.py  # 1000-user load test
├── docs/               # Source documents (add manually)
├── chroma_db/         # Vector database (auto-created)
├── ingest.py          # One-time document ingestion script
└── main.py            # Convenience launcher
```