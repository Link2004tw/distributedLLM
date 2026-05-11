import os
import time
import uuid
from contextlib import asynccontextmanager
from typing import List
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import httpx
from concurrent.futures import ThreadPoolExecutor

from rag.retriever import retriever
from llm.inference import inference_engine


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with httpx.AsyncClient() as client:
        try:
            await client.post(
                f"{MASTER_NODE_URL}/register",
                json={"worker_id": WORKER_ID, "port": WORKER_PORT},
            )
        except Exception:
            pass
    yield


app = FastAPI(lifespan=lifespan)

WORKER_ID = os.environ.get("WORKER_ID", f"worker-{uuid.uuid4().hex[:8]}")
WORKER_PORT = int(os.environ.get("PORT", 8001))
MASTER_NODE_URL = "http://localhost:9000"
EXECUTOR = ThreadPoolExecutor(max_workers=10)

active_connections = 0
avg_latency_ms = 0.0
latencies: List[float] = []


class QueryRequest(BaseModel):
    query: str
    user_id: str = ""
    top_k: int = 3


def process_request_sync(query: str, top_k: int) -> dict:
    start_time = time.time()

    docs = retriever.retrieve(query, top_k=top_k)
    answer = inference_engine.generate_with_context(query, docs)

    latency_ms = (time.time() - start_time) * 1000

    return {
        "answer": answer,
        "sources": docs,
        "latency_ms": latency_ms,
    }


@app.post("/query")
async def handle_query(request: QueryRequest):
    global active_connections, avg_latency_ms, latencies

    active_connections += 1

    try:
        loop = __import__("asyncio").get_event_loop()
        future = loop.run_in_executor(
            EXECUTOR, process_request_sync, request.query, request.top_k
        )
        result = await __import__("asyncio").wrap_future(future)

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
        return {"ready": True, "worker_id": WORKER_ID}
    except Exception as e:
        return {"ready": False, "error": str(e)}


@app.get("/health")
async def health_check():
    return {
        "worker_id": WORKER_ID,
        "healthy": True,
        "active_connections": active_connections,
        "avg_latency_ms": avg_latency_ms,
    }


@app.get("/worker-id")
async def get_worker_id():
    return {"worker_id": WORKER_ID}