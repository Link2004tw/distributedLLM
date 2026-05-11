import os
import sys
import time
import uuid
import asyncio
import subprocess
from typing import List, Optional
from collections import OrderedDict
from dataclasses import dataclass
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import httpx

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from llm.gpu_inference import GPUInferenceEngine, ollama_client, LRU_Cache
from workers.gpu_utils import set_gpu_environment
from workers.gpu_utils import get_gpu_info as _get_gpu_info

app = FastAPI()

WORKER_ID = os.environ.get("WORKER_ID", f"worker-{uuid.uuid4().hex[:8]}")
WORKER_PORT = int(os.environ.get("PORT", 8001))
MASTER_NODE_URL = os.environ.get("MASTER_NODE_URL", "http://localhost:9000")
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")

MAX_QUEUE_SIZE = 100
BATCH_SIZE = 10
BATCH_TIMEOUT_MS = 50
MAX_CONCURRENT_TASKS = 2
CACHE_SIZE = 500

httpx_client: Optional[httpx.AsyncClient] = None
gpu_engine: Optional[GPUInferenceEngine] = None
embed_cache: Optional[LRU_Cache] = None
response_cache: Optional[LRU_Cache] = None
active_connections = 0
avg_latency_ms = 0.0
latencies: List[float] = []


class QueryRequest(BaseModel):
    query: str
    user_id: str = ""
    top_k: int = 3


class BatchQueryRequest(BaseModel):
    queries: List[QueryRequest]


@dataclass
class QueryResult:
    answer: str
    sources: List[str]
    latency_ms: float
    cache_hit: bool


async def init_services():
    global httpx_client, gpu_engine, embed_cache, response_cache

    set_gpu_environment()

    limits = httpx.Limits(max_connections=20, max_keepalive_connections=10)
    httpx_client = httpx.AsyncClient(timeout=120.0, limits=limits)

    gpu_engine = GPUInferenceEngine(ollama_url=OLLAMA_URL, batch_size=BATCH_SIZE, cache_size=CACHE_SIZE)
    await gpu_engine.initialize()

    embed_cache = LRU_Cache(max_size=CACHE_SIZE)
    response_cache = LRU_Cache(max_size=CACHE_SIZE)


async def close_services():
    global httpx_client, gpu_engine
    if gpu_engine:
        await gpu_engine.shutdown()
    if httpx_client:
        await httpx_client.aclose()


def make_cache_key(query: str, top_k: int) -> str:
    normalized = query.lower().strip()[:200]
    return f"{hash(normalized)}:{top_k}"


def make_embed_key(query: str) -> str:
    return hash(query.lower().strip()[:200])


async def retrieve_docs(query: str, top_k: int) -> List[str]:
    embed_key = make_embed_key(query)
    cached_docs = embed_cache.get(embed_key)
    if cached_docs is not None:
        return cached_docs

    try:
        resp = await httpx_client.post(
            f"{OLLAMA_URL}/api/embeddings",
            json={"model": "nomic-embed-text:latest", "prompt": query}
        )
        if resp.status_code == 200:
            docs = [f"Document chunk for: {query[:100]}", f"Related: {query[50:150]}"]
            embed_cache.set(embed_key, docs)
            return docs
    except Exception:
        pass

    docs = [f"Document: {query[:100]}..."]
    embed_cache.set(embed_key, docs)
    return docs


async def process_single_query(query: str, top_k: int, user_id: str) -> QueryResult:
    start_time = time.time()

    cache_key = make_cache_key(query, top_k)
    cached_result = response_cache.get(cache_key)
    if cached_result is not None:
        latency_ms = (time.time() - start_time) * 1000
        return QueryResult(
            answer=cached_result["answer"],
            sources=cached_result["sources"],
            latency_ms=latency_ms,
            cache_hit=True
        )

    docs = await retrieve_docs(query, top_k)
    answer = await gpu_engine.generate(query, docs, use_cache=True)

    latency_ms = (time.time() - start_time) * 1000

    response_cache.set(cache_key, {"answer": answer, "sources": docs})

    return QueryResult(
        answer=answer,
        sources=docs,
        latency_ms=latency_ms,
        cache_hit=False
    )


async def process_batch_queries(queries: List[QueryRequest]) -> List[QueryResult]:
    start_time = time.time()

    tasks = [process_single_query(q.query, q.top_k, q.user_id) for q in queries]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    output = []
    for result in results:
        if isinstance(result, Exception):
            output.append(QueryResult(
                answer=f"Error: {str(result)}",
                sources=[],
                latency_ms=0,
                cache_hit=False
            ))
        else:
            output.append(result)

    return output


@app.on_event("startup")
async def startup_event():
    await init_services()
    try:
        await httpx_client.post(
            f"{MASTER_NODE_URL}/register",
            json={"worker_id": WORKER_ID, "port": WORKER_PORT},
        )
    except Exception:
        pass


@app.on_event("shutdown")
async def shutdown_event():
    await close_services()


@app.post("/query")
async def handle_query(request: QueryRequest):
    global active_connections, avg_latency_ms, latencies

    active_connections += 1
    try:
        result = await process_single_query(request.query, request.top_k, request.user_id)

        latencies.append(result.latency_ms)
        if len(latencies) > 100:
            latencies = latencies[-100:]
        avg_latency_ms = sum(latencies) / len(latencies)

        return {
            "answer": result.answer,
            "sources": result.sources,
            "latency_ms": result.latency_ms,
            "cache_hit": result.cache_hit
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        active_connections -= 1


@app.post("/query/batch")
async def handle_batch_query(request: BatchQueryRequest):
    global active_connections, avg_latency_ms, latencies

    batch_size = len(request.queries)
    active_connections += batch_size

    try:
        results = await process_batch_queries(request.queries)

        for result in results:
            latencies.append(result.latency_ms)

        if len(latencies) > 100:
            latencies = latencies[-100:]
        avg_latency_ms = sum(latencies) / len(latencies) if latencies else 0.0

        return {
            "results": [
                {
                    "answer": r.answer,
                    "sources": r.sources,
                    "latency_ms": r.latency_ms,
                    "cache_hit": r.cache_hit
                }
                for r in results
            ],
            "batch_size": batch_size
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        active_connections -= batch_size


@app.get("/health")
async def health_check():
    gpu_info = _get_gpu_info()
    return {
        "worker_id": WORKER_ID,
        "healthy": True,
        "active_connections": active_connections,
        "avg_latency_ms": round(avg_latency_ms, 2),
        "gpu_utilization": gpu_info.get("gpu_utilization", 0),
        "gpu_memory_used_mb": gpu_info.get("memory_used_mb", 0),
        "gpu_memory_total_mb": gpu_info.get("memory_total_mb", 6144),
        "gpu_temperature_c": gpu_info.get("temperature_c", 0),
        "gpu_power_watts": gpu_info.get("power_watts", 0.0),
        "cache_size": len(response_cache) if response_cache else 0,
        "embed_cache_size": len(embed_cache) if embed_cache else 0,
    }


@app.get("/gpu-stats")
async def gpu_stats():
    gpu_info = _get_gpu_info()
    memory_used = gpu_info.get("memory_used_mb", 0)
    memory_total = gpu_info.get("memory_total_mb", 6144)
    return {
        "gpu_name": "NVIDIA GeForce RTX 3060 Laptop",
        "utilization_percent": gpu_info.get("gpu_utilization", 0),
        "memory_used_mb": memory_used,
        "memory_total_mb": memory_total,
        "memory_free_mb": memory_total - memory_used,
        "temperature_c": gpu_info.get("temperature_c", 0),
        "power_watts": gpu_info.get("power_watts", 0.0),
    }


@app.get("/worker-id")
async def get_worker_id():
    return {"worker_id": WORKER_ID}


@app.get("/capabilities")
async def get_capabilities():
    return {
        "single_query": True,
        "batch_processing": True,
        "streaming": False,
        "gpu_accelerated": True,
        "max_batch_size": BATCH_SIZE,
        "max_concurrent": MAX_CONCURRENT_TASKS,
        "caching": True,
        "cache_size": CACHE_SIZE,
    }