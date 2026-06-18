import logging
import os
import time
import uuid
import asyncio
import subprocess
from collections import OrderedDict
from dataclasses import dataclass
from typing import List, Optional, AsyncIterator
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
import httpx

logger = logging.getLogger(__name__)

from rag.retriever import Retriever, retriever
from llm.inference import InferenceEngine, inference_engine


WORKER_ID = os.environ.get("WORKER_ID", f"worker-{uuid.uuid4().hex[:8]}")
WORKER_PORT = int(os.environ.get("PORT", 8001))
MASTER_NODE_URL = os.environ.get("MASTER_NODE_URL", "http://localhost:9000")
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")

MAX_QUEUE_SIZE = 1000
BATCH_SIZE = 10
BATCH_TIMEOUT_MS = 50
MAX_CONCURRENT_TASKS = int(os.environ.get("MAX_CONCURRENT_TASKS", "250"))
CACHE_SIZE = 500
BACKPRESSURE_QUEUE_SIZE = int(os.environ.get("BACKPRESSURE_QUEUE_SIZE", "1000"))
EMBED_BATCH_SIZE = 20

request_semaphore: Optional[asyncio.Semaphore] = None
httpx_client: Optional[httpx.AsyncClient] = None
active_connections = 0
active_connections_lock: Optional[asyncio.Lock] = None
avg_latency_ms = 0.0
latencies: List[float] = []
latencies_lock: Optional[asyncio.Lock] = None
embed_cache: dict = {}
response_cache: dict = {}
embed_cache_lock: Optional[asyncio.Lock] = None
response_cache_lock: Optional[asyncio.Lock] = None

app = FastAPI()


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
    retrieval_time_ms: float = 0.0


def get_gpu_info() -> dict:
    try:
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu,power.draw",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            parts = result.stdout.strip().split(", ")
            return {
                "gpu_utilization": int(parts[0]),
                "memory_used_mb": int(parts[1]),
                "memory_total_mb": int(parts[2]),
                "temperature_c": int(parts[3]),
                "power_watts": float(parts[4]) if len(parts) > 4 else 0.0
            }
    except Exception:
        logger.debug("Failed to query nvidia-smi GPU info: %s", e)
    return {"gpu_utilization": 0, "memory_used_mb": 0, "memory_total_mb": 6144, "temperature_c": 0, "power_watts": 0.0}


def get_cache_key(query: str, top_k: int) -> str:
    normalized = query.lower().strip()[:200]
    return f"response:{hash(normalized)}:{top_k}"


def get_embed_key(query: str) -> str:
    return f"embed:{hash(query.lower().strip()[:200])}"


async def init_services():
    global httpx_client, request_semaphore, active_connections_lock, latencies_lock
    global embed_cache_lock, response_cache_lock
    limits = httpx.Limits(max_connections=500, max_keepalive_connections=250)
    httpx_client = httpx.AsyncClient(timeout=3600.0, limits=limits)
    request_semaphore = asyncio.Semaphore(MAX_CONCURRENT_TASKS)
    active_connections_lock = asyncio.Lock()
    latencies_lock = asyncio.Lock()
    embed_cache_lock = asyncio.Lock()
    response_cache_lock = asyncio.Lock()
    await inference_engine.init_client()


async def close_services():
    global httpx_client
    if httpx_client:
        await httpx_client.aclose()
    await inference_engine.close()


async def warmup():
    print(f"[{WORKER_ID}] Warming up inference engine...")
    try:
        await inference_engine.generate("ping")
        print(f"[{WORKER_ID}] Warmup complete")
    except Exception as e:
        logger.warning("[%s] Warmup failed: %s", WORKER_ID, e)


async def retrieve_docs(query: str, top_k: int) -> List[str]:
    embed_key = get_embed_key(query)

    if embed_key in embed_cache:
        return embed_cache[embed_key]

    try:
        loop = asyncio.get_event_loop()
        docs = await loop.run_in_executor(
            None, lambda: retriever.retrieve(query, top_k=top_k)
        )
        docs_text = [doc.page_content if hasattr(doc, 'page_content') else str(doc) for doc in docs]
        if docs_text:
            async with embed_cache_lock:
                if len(embed_cache) >= CACHE_SIZE:
                    del embed_cache[next(iter(embed_cache))]
                embed_cache[embed_key] = docs_text
        return docs_text
    except Exception as e:
        logger.warning("RAG retrieval error: %s", e)
        return []


async def retrieve_docs_batch(queries: List[str], top_k: int) -> List[List[str]]:
    cached_results = []
    queries_to_fetch = []
    indices_to_fetch = []

    for i, q in enumerate(queries):
        embed_key = get_embed_key(q)
        if embed_key in embed_cache:
            cached_results.append((i, embed_cache[embed_key]))
        else:
            queries_to_fetch.append(q)
            indices_to_fetch.append(i)

    if not queries_to_fetch:
        results = [[] for _ in queries]
        for idx, cached in cached_results:
            results[idx] = cached
        return results

    try:
        loop = asyncio.get_event_loop()
        fresh_results = await loop.run_in_executor(
            None, lambda: retriever.retrieve_batch(queries_to_fetch, top_k=top_k)
        )
    except Exception as e:
        logger.warning("Batch retrieval error: %s", e)
        fresh_results = [[] for _ in queries_to_fetch]

    for idx, query, docs in zip(indices_to_fetch, queries_to_fetch, fresh_results):
        embed_key = get_embed_key(query)
        if docs:
            async with embed_cache_lock:
                if len(embed_cache) >= CACHE_SIZE:
                    del embed_cache[next(iter(embed_cache))]
                embed_cache[embed_key] = docs

    results = [[] for _ in queries]
    for idx, cached in cached_results:
        results[idx] = cached
    for idx, docs in zip(indices_to_fetch, fresh_results):
        results[idx] = docs

    return results


async def process_single_query(query: str, top_k: int, user_id: str) -> dict:
    start_time = time.time()

    cache_key = get_cache_key(query, top_k)
    if cache_key in response_cache:
        cached = response_cache[cache_key].copy()
        cached["latency_ms"] = (time.time() - start_time) * 1000
        cached["cache_hit"] = True
        cached["retrieval_time_ms"] = 0.0
        return cached

    async with request_semaphore:
        retrieval_start = time.time()
        docs = await retrieve_docs(query, top_k)
        retrieval_time_ms = (time.time() - retrieval_start) * 1000

        if not docs:
            answer = "I don't have relevant documents to answer this question. Please try a different query."
        else:
            try:
                answer = await inference_engine.generate_with_context(query, docs)
            except Exception as e:
                logger.warning("LLM inference error: %s", e)
                return {
                    "worker_id": WORKER_ID,
                    "answer": "Service temporarily unavailable. Please retry.",
                    "sources": docs,
                    "latency_ms": (time.time() - start_time) * 1000,
                    "cache_hit": False,
                    "retrieval_time_ms": retrieval_time_ms,
                }

        latency_ms = (time.time() - start_time) * 1000

        result = {
            "worker_id": WORKER_ID,
            "answer": answer,
            "sources": docs,
            "latency_ms": latency_ms,
            "cache_hit": False,
            "retrieval_time_ms": retrieval_time_ms,
        }

        if docs:
            async with response_cache_lock:
                if len(response_cache) >= CACHE_SIZE:
                    del response_cache[next(iter(response_cache))]
                response_cache[cache_key] = result.copy()

        return result


async def process_batch_queries(queries: List[QueryRequest]) -> List[dict]:
    if not queries:
        return []

    start_time = time.time()
    query_strs = [q.query for q in queries]
    top_k = max(q.top_k for q in queries) if queries else 3

    docs_batch = await retrieve_docs_batch(query_strs, top_k)

    tasks = []
    for i, (query, docs) in enumerate(zip(query_strs, docs_batch)):
        tasks.append(process_batch_single(query, docs, queries[i].top_k, start_time))

    results = await asyncio.gather(*tasks, return_exceptions=True)

    output = []
    for i, result in enumerate(results):
        if isinstance(result, Exception):
            output.append({
                "answer": f"Error: {str(result)}",
                "sources": [],
                "latency_ms": (time.time() - start_time) * 1000,
                "cache_hit": False,
            })
        else:
            output.append(result)
    return output


async def process_batch_single(query: str, docs: List[str], top_k: int, batch_start: float) -> dict:
    cache_key = get_cache_key(query, top_k)
    if cache_key in response_cache:
        cached = response_cache[cache_key].copy()
        cached["latency_ms"] = (time.time() - batch_start) * 1000
        cached["cache_hit"] = True
        return cached

    if not docs:
        answer = "I don't have relevant documents to answer this question."
    else:
        try:
            answer = await inference_engine.generate_with_context(query, docs)
        except Exception as e:
            logger.warning("LLM inference error in batch: %s", e)
            answer = "Service temporarily unavailable. Please retry."

    result = {
        "worker_id": WORKER_ID,
        "answer": answer,
        "sources": docs,
        "latency_ms": (time.time() - batch_start) * 1000,
        "cache_hit": False,
    }

    if docs and answer != "Service temporarily unavailable. Please retry.":
        async with response_cache_lock:
            if len(response_cache) >= CACHE_SIZE:
                del response_cache[next(iter(response_cache))]
            response_cache[cache_key] = result.copy()

    return result


async def process_batch_optimized(queries: List[QueryRequest]) -> List[dict]:
    if not queries:
        return []

    start_time = time.time()
    query_strs = [q.query for q in queries]
    top_k = max(q.top_k for q in queries) if queries else 3

    docs_batch = await retrieve_docs_batch(query_strs, top_k)

    cache_hits = []
    cache_misses = []
    cache_indices = []
    miss_queries = []
    miss_docs = []

    for i, (query, docs) in enumerate(zip(query_strs, docs_batch)):
        cache_key = get_cache_key(query, queries[i].top_k)
        if cache_key in response_cache:
            cache_hits.append((i, response_cache[cache_key].copy(), docs))
        else:
            cache_misses.append((i, query, docs, queries[i].top_k))
            cache_indices.append(i)
            miss_queries.append(query)
            miss_docs.append(docs)

    results = [{} for _ in queries]

    for idx, cached, docs in cache_hits:
        cached["latency_ms"] = (time.time() - start_time) * 1000
        cached["cache_hit"] = True
        results[idx] = cached

    if miss_queries:
        try:
            answers = await inference_engine.generate_batch(miss_queries, miss_docs)
        except Exception as e:
            logger.warning("Batch generation error: %s", e)
            answers = ["Service temporarily unavailable. Please retry." for _ in miss_queries]

        for (idx, query, docs, tk), answer in zip(cache_misses, answers):
            result = {
                "worker_id": WORKER_ID,
                "answer": answer,
                "sources": docs,
                "latency_ms": (time.time() - start_time) * 1000,
                "cache_hit": False,
            }
            if docs and answer != "Service temporarily unavailable. Please retry.":
                async with response_cache_lock:
                    if len(response_cache) >= CACHE_SIZE:
                        del response_cache[next(iter(response_cache))]
                    response_cache[get_cache_key(query, tk)] = result.copy()
            results[idx] = result

    return results


@app.on_event("startup")
async def startup_event():
    await init_services()
    await warmup()
    try:
        await httpx_client.post(
            f"{MASTER_NODE_URL}/register",
            json={"worker_id": WORKER_ID, "port": WORKER_PORT},
        )
    except Exception:
        logger.warning("Failed to register worker %s with master at %s", WORKER_ID)


@app.on_event("shutdown")
async def shutdown_event():
    await close_services()


@app.post("/query")
async def handle_query(request: QueryRequest):
    global active_connections, avg_latency_ms, latencies

    async with active_connections_lock:
        if active_connections >= BACKPRESSURE_QUEUE_SIZE:
            raise HTTPException(
                status_code=503,
                detail="Worker at capacity. Request rejected due to backpressure. Please retry."
            )
        active_connections += 1

    try:
        result = await process_single_query(request.query, request.top_k, request.user_id)
        async with latencies_lock:
            latencies.append(result["latency_ms"])
            if len(latencies) > 100:
                latencies = latencies[-100:]
            avg_latency_ms = sum(latencies) / len(latencies)
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        async with active_connections_lock:
            active_connections -= 1


@app.post("/query/batch")
async def handle_batch_query(request: BatchQueryRequest):
    global active_connections, avg_latency_ms, latencies

    batch_size = len(request.queries)

    async with active_connections_lock:
        if active_connections + batch_size > BACKPRESSURE_QUEUE_SIZE:
            raise HTTPException(
                status_code=503,
                detail="Worker at capacity. Batch request rejected."
            )
        active_connections += batch_size

    try:
        results = await process_batch_optimized(request.queries)
        async with latencies_lock:
            for result in results:
                latencies.append(result.get("latency_ms", 0))
            if len(latencies) > 100:
                latencies = latencies[-100:]
            avg_latency_ms = sum(latencies) / len(latencies) if latencies else 0.0

        return {
            "results": [
                {
                    "answer": r["answer"],
                    "sources": r["sources"],
                    "latency_ms": r["latency_ms"],
                    "cache_hit": r["cache_hit"],
                }
                for r in results
            ],
            "batch_size": batch_size,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        async with active_connections_lock:
            active_connections -= batch_size


@app.get("/ready")
async def ready_check():
    try:
        await inference_engine.generate("ping")
        return {"ready": True, "worker_id": WORKER_ID}
    except Exception as e:
        return {"ready": False, "error": str(e), "worker_id": WORKER_ID}


@app.get("/health")
async def health_check():
    gpu_info = get_gpu_info()
    queue_available = BACKPRESSURE_QUEUE_SIZE - active_connections
    return {
        "worker_id": WORKER_ID,
        "healthy": True,
        "active_connections": active_connections,
        "max_concurrent": MAX_CONCURRENT_TASKS,
        "queue_available": max(0, queue_available),
        "avg_latency_ms": round(avg_latency_ms, 2),
        "gpu_utilization": gpu_info.get("gpu_utilization", 0),
        "gpu_memory_used_mb": gpu_info.get("memory_used_mb", 0),
        "gpu_memory_total_mb": gpu_info.get("memory_total_mb", 6144),
        "gpu_temperature_c": gpu_info.get("temperature_c", 0),
        "gpu_power_watts": gpu_info.get("power_watts", 0.0),
        "cache_size": len(response_cache),
        "embed_cache_size": len(embed_cache),
    }


@app.get("/gpu-stats")
async def gpu_stats():
    gpu_info = get_gpu_info()
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
        "batch_optimized": True,
        "streaming": True,
        "gpu_accelerated": True,
        "max_batch_size": BATCH_SIZE,
        "max_concurrent": MAX_CONCURRENT_TASKS,
        "caching": True,
        "cache_size": CACHE_SIZE,
        "embed_batching": True,
    }


@app.post("/query/fallback")
async def handle_fallback_query(request: QueryRequest):
    return {
        "worker_id": WORKER_ID,
        "answer": "Service temporarily unavailable. Please retry.",
        "sources": [],
        "latency_ms": 0,
        "retrieval_time_ms": 0,
        "cache_hit": False,
    }


async def stream_generator(query: str, top_k: int) -> AsyncIterator[str]:
    try:
        docs = await retrieve_docs(query, top_k)

        if not docs:
            yield "data: {\"type\": \"done\", \"content\": \"I don't have relevant documents.\"}\n\n"
            return

        answer = await inference_engine.generate_with_context(query, docs)
        yield f"data: {{\"type\": \"chunk\", \"content\": {repr(answer)}}}\n\n"
        yield "data: {\"type\": \"done\", \"content\": null}\n\n"

    except Exception as e:
        yield f"data: {{\"type\": \"error\", \"content\": {repr(str(e))}}}\n\n"


@app.post("/query/stream")
async def handle_stream_query(request: QueryRequest):
    return StreamingResponse(
        stream_generator(request.query, request.top_k),
        media_type="text/event-stream"
    )
