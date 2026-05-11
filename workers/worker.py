import os
import time
import uuid
import subprocess
from typing import List, Optional
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import httpx
from asyncio import Queue, gather

from rag.retriever import retriever
from llm.inference import inference_engine

app = FastAPI()

WORKER_ID = os.environ.get("WORKER_ID", f"worker-{uuid.uuid4().hex[:8]}")
WORKER_PORT = int(os.environ.get("PORT", 8001))
MASTER_NODE_URL = "http://localhost:9000"
CUDA_VISIBLE_DEVICES = os.environ.get("CUDA_VISIBLE_DEVICES", "0")

MAX_QUEUE_SIZE = 100
BATCH_SIZE = 10
BATCH_TIMEOUT_MS = 100
MAX_CONCURRENT_TASKS = 2

query_queue: Queue = None
active_connections = 0
avg_latency_ms = 0.0
latencies: List[float] = []
embed_cache: dict = {}
response_cache: dict = {}
CACHE_SIZE = 500


class QueryRequest(BaseModel):
    query: str
    user_id: str = ""
    top_k: int = 3


def get_gpu_info() -> dict:
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu",
             "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True,
            timeout=5
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
        cached = response_cache[cache_key]
        cached["latency_ms"] = (time.time() - start_time) * 1000
        cached["cache_hit"] = True
        return cached

    embed_cache_key = query
    if embed_cache_key in embed_cache:
        docs = embed_cache[embed_cache_key]
    else:
        docs = retriever.retrieve(query, top_k=top_k)
        if len(embed_cache) >= CACHE_SIZE:
            oldest_key = next(iter(embed_cache))
            del embed_cache[oldest_key]
        embed_cache[embed_cache_key] = docs

    answer = inference_engine.generate_with_context(query, docs)

    latency_ms = (time.time() - start_time) * 1000

    result = {
        "answer": answer,
        "sources": docs,
        "latency_ms": latency_ms,
        "cache_hit": False
    }

    if len(response_cache) >= CACHE_SIZE:
        oldest_key = next(iter(response_cache))
        del response_cache[oldest_key]
    response_cache[cache_key] = result

    return result


@app.on_event("startup")
async def startup_event():
    global query_queue
    query_queue = Queue(maxsize=MAX_QUEUE_SIZE)
    async with httpx.AsyncClient() as client:
        try:
            await client.post(
                f"{MASTER_NODE_URL}/register",
                json={"worker_id": WORKER_ID, "port": WORKER_PORT},
            )
        except Exception:
            pass


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


@app.get("/health")
async def health_check():
    gpu_info = get_gpu_info()
    return {
        "worker_id": WORKER_ID,
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
    return {"worker_id": WORKER_ID}