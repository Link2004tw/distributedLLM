# Distributed LLM Inference System with RAG and Load Balancing

## Overview

This project implements a distributed computing system designed to handle 1000+ concurrent user requests involving Large Language Model (LLM) inference augmented with Retrieval-Augmented Generation (RAG). The system simulates a real-world AI serving infrastructure where requests require heavy computation and must be distributed dynamically across multiple processing nodes.

The system is entirely Python-based, runs locally on a single machine, and uses process-level isolation to simulate a genuine distributed environment — each worker node is a separate OS process with its own HTTP server, its own LLM connection, and its own request queue.

---

## Architecture

The system is organized into five distinct layers, each running as an independent component:

### 1. Client Layer
Simulates 1000+ concurrent users using Python's `threading` module. Each thread represents a user sending an HTTP POST request to the Load Balancer. The client layer measures per-request latency and aggregates throughput metrics after the load test completes.

### 2. Load Balancer (FastAPI — Port 8000)
A FastAPI HTTP server that acts as the single entry point for all incoming requests. It implements three routing strategies:
- **Round Robin** — distributes requests evenly across all active workers in sequence
- **Least Connections** — routes each new request to the worker currently handling the fewest active requests
- **Load-Aware Routing** — extends least connections with worker health scoring based on recent latency

The Load Balancer maintains a live registry of active worker nodes. If the Master Node marks a worker as unhealthy, the Load Balancer removes it from the routing pool immediately.

### 3. Master Node (FastAPI — Port 9000)
The Master Node is the system's health monitor and orchestrator. It runs a background thread that periodically sends heartbeat checks to every registered worker. If a worker fails to respond within a timeout threshold, the Master Node marks it as failed, notifies the Load Balancer to stop routing to it, and triggers task reassignment for any in-flight requests on that worker.

The Master Node also exposes a metrics dashboard endpoint that reports real-time system performance: throughput, average latency, per-worker load, and failure events.

### 4. GPU Worker Nodes (FastAPI — Ports 8001–8004)
Each worker is a completely independent FastAPI process. On startup, each worker:
1. Connects to the local Ollama instance to access the LLM
2. Loads the BGE-M3 embedding model via `sentence-transformers`
3. Connects to the shared ChromaDB vector database
4. Registers itself with the Master Node

When a request arrives, the worker executes the full RAG + LLM pipeline:
1. Embed the incoming query using BGE-M3
2. Retrieve the top-K most relevant document chunks from ChromaDB
3. Construct a context-augmented prompt
4. Send the prompt to the LLM via Ollama and stream back the response
5. Return the result with latency metadata

Each worker handles incoming requests concurrently using FastAPI's async request handling backed by a thread pool executor for the blocking Ollama calls.

### 5. RAG Pipeline
The RAG pipeline is shared logic used by every worker node. It consists of two phases:
- **Indexing (offline)** — a one-time ingestion script reads source documents, splits them into chunks, embeds each chunk with BGE-M3, and stores the vectors in ChromaDB on disk
- **Retrieval (online)** — at inference time, the query is embedded and the top-K most semantically similar chunks are retrieved from ChromaDB using cosine similarity search

---

## Fault Tolerance

The system implements three fault tolerance mechanisms:

1. **Heartbeat-based failure detection** — the Master Node pings each worker every 5 seconds; a worker that misses 3 consecutive heartbeats is declared failed
2. **Automatic task reassignment** — in-flight requests on a failed worker are requeued and redistributed to healthy workers via the Load Balancer
3. **Load Balancer resilience** — the routing pool is updated in real time; the Load Balancer never routes to a worker that the Master Node has declared unhealthy

---

## Data Flow (Single Request)

```
User (thread)
  → HTTP POST /query  →  Load Balancer (port 8000)
                              ↓  selects worker (least connections)
                         Worker Node (port 800X)
                              ↓  embed query (BGE-M3)
                         ChromaDB  →  top-K chunks
                              ↓  build augmented prompt
                         Ollama (LLM)  →  generated answer
                              ↓  return response + latency
  ← HTTP 200 JSON  ←  Load Balancer  ←  Worker Node
```

---

## Scope and Limitations

- All components run on a single physical machine; "distributed" is simulated at the process level
- Ollama serializes LLM inference internally per instance; true GPU parallelism would require multiple physical GPUs
- ChromaDB is shared across workers via a single on-disk database; a production system would use a dedicated vector DB server
- The current implementation does not persist request logs across restarts
