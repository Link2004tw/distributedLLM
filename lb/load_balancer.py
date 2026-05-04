import asyncio
import time
from typing import Dict, List, Optional
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
import httpx

from common.models import (
    QueryRequest,
    QueryResponse,
    WorkerInfo,
    RoutingStrategy,
    RequeueRequest,
)

app = FastAPI()

ACTIVE_WORKERS: Dict[str, WorkerInfo] = {}
ROUND_ROBIN_INDEX: int = 0
REQUEUE_QUEUE: List[RequeueRequest] = []
MASTER_NODE_URL = "http://localhost:9000"

STRATEGY = RoutingStrategy.LEAST_CONNECTIONS


@app.on_event("startup")
async def startup_event():
    asyncio.create_task(sync_with_master())


async def sync_with_master():
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(f"{MASTER_NODE_URL}/workers")
            if response.status_code == 200:
                workers = response.json().get("workers", [])
                ACTIVE_WORKERS.clear()
                for w in workers:
                    ACTIVE_WORKERS[w["worker_id"]] = WorkerInfo(**w)
    except Exception:
        pass


def select_worker(strategy: RoutingStrategy) -> Optional[WorkerInfo]:
    healthy = [w for w in ACTIVE_WORKERS.values() if w.healthy]
    if not healthy:
        return None

    if strategy == RoutingStrategy.ROUND_ROBIN:
        global ROUND_ROBIN_INDEX
        worker = healthy[ROUND_ROBIN_INDEX % len(healthy)]
        ROUND_ROBIN_INDEX += 1
        return worker

    elif strategy == RoutingStrategy.LEAST_CONNECTIONS:
        return min(healthy, key=lambda w: w.active_connections)

    elif strategy == RoutingStrategy.LOAD_AWARE:
        scored = [(w, w.active_connections + w.avg_latency_ms / 100) for w in healthy]
        return min(scored, key=lambda x: x[1])[0]

    return healthy[0]


@app.post("/query")
async def handle_query(request: QueryRequest):
    worker = select_worker(request.strategy)
    if not worker:
        raise HTTPException(status_code=503, detail="No healthy workers available")

    worker.active_connections += 1

    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"http://{worker.host}:{worker.port}/query",
                json={"query": request.query, "user_id": request.user_id, "top_k": request.top_k},
            )
            response.raise_for_status()
            result = response.json()
            return result
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"Worker error: {str(e)}")
    finally:
        worker.active_connections -= 1


@app.get("/workers")
async def list_workers():
    return {"workers": [w.__dict__ for w in ACTIVE_WORKERS.values()]}


@app.get("/health")
async def health_check():
    return {"status": "ok", "workers": len(ACTIVE_WORKERS)}


@app.post("/strategy")
async def set_strategy(strategy: RoutingStrategy):
    global STRATEGY
    STRATEGY = strategy
    return {"strategy": STRATEGY}


@app.post("/worker/unhealthy")
async def mark_worker_unhealthy(data: dict):
    worker_id = data.get("worker_id")
    if worker_id in ACTIVE_WORKERS:
        ACTIVE_WORKERS[worker_id].healthy = False
        return {"status": "updated"}
    return {"status": "not_found"}