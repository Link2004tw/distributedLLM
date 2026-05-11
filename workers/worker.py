import os
import time
import uuid
import subprocess
from contextlib import asynccontextmanager
from typing import List
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import httpx
import asyncio
from asyncio import Queue

from rag.retriever import retriever
from llm.inference import inference_engine


WORKER_ID = os.environ.get("WORKER_ID", f"worker-{uuid.uuid4().hex[:8]}")
WORKER_PORT = int(os.environ.get("PORT", 8001))
MASTER_NODE_URL = os.environ.get("MASTER_NODE_URL", "http://localhost:9000")
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")  # <-- new

MAX_QUEUE_SIZE = 100
BATCH_SIZE = 10
BATCH_TIMEOUT_MS = 100
MAX_CONCURRENT_TASKS = 2
CACHE_SIZE = 500

query_queue: Queue = None
active_connections = 0
avg_latency_ms = 0.0
latencies: List[float] = []
embed_cache: dict = {}
response_cache: dict = {}


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Pass OLLAMA_URL to inference engine so it hits the right instance
    inference_engine.set_base_url(OLLAMA_URL)
    retriever.set_base_url(OLLAMA_URL)  # if retriever also uses Ollama for embeddings

    async with httpx.AsyncClient() as client:
        try:
            await client.post(
                f"{MASTER_NODE_URL}/register",
                json={
                    "worker_id": WORKER_ID,
                    "port": WORKER_PORT,
                    "ollama_url": OLLAMA_URL,
                },
            )
        except Exception:
            pass
    yield


app = FastAPI(lifespan=lifespan)


class QueryRequest(BaseModel):
    query: str
    user_id: str = ""
    top_k: int = 3


def get_gpu_info() -> dict:
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            parts = result.stdout.strip().split(", ")
            return {
                "gpu_utilization": int(parts[0]),
                "memory_used_mb": int(parts[1]),
                "memory_total_mb": int(parts[2]),
                "temperature_c": int(parts[3])
            }
    except Exception:
        pass
    return {"gpu_utilization": 0, "memory_used_mb": 0, "memory_total_mb": 0, "temperature_c": 0}


def get_cache_key(query: str, top_k: int) -> str:
    return f"{query[:100]}:{top_k}"


async def process_request_async(query: str, top_k: int, request_id: str) -> dict:
    start_time = time.time()

    cache_key = get_cache_key(query, top_k)
    if cache_key in response_cache:
        cached = response_cache[cache_key].copy()
        cached["latency_ms"] = (time.time() - start_time) * 1000
        cached["cache_hit"] = True
        return cached

    if query in embed_cache:
        docs = embed_cache[query]
    else:
        docs = retriever.retrieve(query, top_k=top_k)
        if len(embed_cache) >= CACHE_SIZE:
            del embed_cache[next(iter(embed_cache))]
        embed_cache[query] = docs

    answer = inference_engine.generate_with_context(query, docs)
    latency_ms = (time.time() - start_time) * 1000

    result = {
        "answer": answer,
        "sources": docs,
        "latency_ms": latency_ms,
        "cache_hit": False,
        "worker_id": WORKER_ID,
        "ollama_url": OLLAMA_URL,
    }

    if len(response_cache) >= CACHE_SIZE:
        del response_cache[next(iter(response_cache))]
    response_cache[cache_key] = result

    return result


@app.on_event("startup")
async def startup_event():
    global query_queue
    query_queue = Queue(maxsize=MAX_QUEUE_SIZE)

    print(f"[{WORKER_ID}] Warming up inference engine...")
    try:
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, lambda: inference_engine.generate("ping"))
        print(f"[{WORKER_ID}] Warmup complete")
    except Exception as e:
        print(f"[{WORKER_ID}] Warmup failed: {e}")


@app.post("/query")
async def handle_query(request: QueryRequest):
    global active_connections, avg_latency_ms, latencies

    active_connections += 1
    try:
        result = await process_request_async(request.query, request.top_k, request.user_id)
        latencies.append(result["latency_ms"])
        if len(latencies) > 100:
            latencies = latencies[-100:]
        avg_latency_ms = sum(latencies) / len(latencies)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        active_connections -= 1


@app.get("/ready")
async def ready_check():
    try:
        loop = __import__("asyncio").get_event_loop()
        future = loop.run_in_executor(None, lambda: inference_engine.generate("ping"))
        result = await __import__("asyncio").wait_for(future, timeout=15.0)
        return {"ready": True, "worker_id": WORKER_ID, "ollama_url": OLLAMA_URL}
    except Exception as e:
        return {"ready": False, "error": str(e), "ollama_url": OLLAMA_URL}


@app.get("/health")
async def health_check():
    gpu_info = get_gpu_info()
    return {
        "worker_id": WORKER_ID,
        "ollama_url": OLLAMA_URL,
        "healthy": True,
        "active_connections": active_connections,
        "avg_latency_ms": avg_latency_ms,
        "gpu_utilization": gpu_info.get("gpu_utilization", 0),
        "gpu_memory_used_mb": gpu_info.get("memory_used_mb", 0),
        "gpu_memory_total_mb": gpu_info.get("memory_total_mb", 0),
        "gpu_temperature_c": gpu_info.get("temperature_c", 0),
        "cache_size": len(response_cache),
        "embed_cache_size": len(embed_cache),
    }


@app.get("/worker-id")
async def get_worker_id():
    return {"worker_id": WORKER_ID, "ollama_url": OLLAMA_URL}