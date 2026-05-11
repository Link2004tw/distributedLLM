import os
import time
import uuid
import asyncio
from typing import List, Optional
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import httpx
from concurrent.futures import ThreadPoolExecutor

from workers.gpu_worker import GPUWorker

app = FastAPI()

WORKER_ID = os.environ.get("WORKER_ID", f"worker-{uuid.uuid4().hex[:8]}")
WORKER_PORT = int(os.environ.get("WORKER_PORT", 8001))
MASTER_URL = os.environ.get("MASTER_URL", "http://127.0.0.1:9000")
EXECUTOR = ThreadPoolExecutor(max_workers=10)

worker_instance = GPUWorker(worker_id=WORKER_ID)

active_connections = 0
avg_latency_ms = 0.0
latencies: List[float] = []

class QueryRequest(BaseModel):
    id: Optional[str] = None
    request_id: Optional[str] = None
    client_id: Optional[int] = None
    query: str
    top_k: int = 3

@app.on_event("startup")
async def startup_event():
    async with httpx.AsyncClient() as client:
        try:
            await client.post(
                f"{MASTER_URL}/workers/register",
                json={"worker_id": WORKER_ID, "port": WORKER_PORT, "host": "127.0.0.1"},
                timeout=5.0
            )
        except Exception as e:
            print(f"Failed to register with master: {e}")

@app.post("/query")
async def handle_query(request: QueryRequest):
    global active_connections, avg_latency_ms, latencies

    active_connections += 1
    req_id = request.request_id or request.id or str(uuid.uuid4())

    try:
        loop = asyncio.get_event_loop()
        future = loop.run_in_executor(
            EXECUTOR, worker_instance.process, request.query, req_id
        )
        result = await future

        latencies.append(result["latency_ms"])
        if len(latencies) > 100:
            latencies = latencies[-100:]
        avg_latency_ms = sum(latencies) / len(latencies)

        return result
    except Exception as e:
        return {
            "request_id": req_id,
            "worker_id": WORKER_ID,
            "answer": f"Error: {str(e)}",
            "sources": [],
            "latency_ms": 0,
            "status": "error"
        }
    finally:
        active_connections -= 1

@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "worker_id": WORKER_ID,
        "port": WORKER_PORT
    }