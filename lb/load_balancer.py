import asyncio
import time
import logging
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
from master.scheduler import WorkerScheduler

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("load_balancer")
app = FastAPI()

ACTIVE_WORKERS: Dict[str, WorkerInfo] = {}
MASTER_NODE_URL = "http://localhost:9000"
STRATEGY = RoutingStrategy.LEAST_CONNECTIONS
SYNC_INTERVAL_SECONDS = 5

scheduler= WorkerScheduler(workers=ACTIVE_WORKERS)

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(sync_workers_loop())

async def sync_workers_loop():
    """
    Continuously syncs worker list from the master node every SYNC_INTERVAL_SECONDS.
    Keeps ACTIVE_WORKERS and the scheduler up-to-date as nodes join or leave.
    """
    while True:
        await _fetch_workers_from_master()
        await asyncio.sleep(SYNC_INTERVAL_SECONDS)

async def _fetch_workers_from_master():
    """Pull the latest worker registry from the master node."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{MASTER_NODE_URL}/workers")
            if response.status_code == 200:
                workers_data = response.json().get("workers", [])
                ACTIVE_WORKERS.clear()
                for w in workers_data:
                    ACTIVE_WORKERS[w["worker_id"]] = WorkerInfo(**w)
                # Keep scheduler in sync with the updated worker dict
                scheduler.update_workers(ACTIVE_WORKERS)
                logger.info(f"Synced {len(ACTIVE_WORKERS)} workers from master")
    except Exception as e:
        logger.warning(f"Could not sync with master: {e}")

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


@app.post("/query", response_model=QueryResponse)
async def handle_query(request: QueryRequest):
    """
    Main entry point for all client requests.
    1. Picks a strategy (per-request override or global default).
    2. Delegates worker selection to WorkerScheduler.
    3. Forwards the request to the chosen worker.
    4. Tracks active connections so least-connections stays accurate.
    """
    strategy = request.strategy if request.strategy else STRATEGY

    worker = scheduler.select_worker(strategy)
    if not worker:
        logger.error("No healthy workers available to handle request")
        raise HTTPException(status_code=503, detail="No healthy workers available")

    worker.active_connections += 1
    logger.info(
        f"Routing user={request.user_id} to worker={worker.worker_id} "
        f"(strategy={strategy}, connections={worker.active_connections})"
    )
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            response = await client.post(
                f"http://{worker.host}:{worker.port}/query",
                json={"query": request.query, "user_id": request.user_id, "top_k": request.top_k},
            )
            response.raise_for_status()
            result = response.json()
            return result
    except httpx.TimeoutException:
        logger.error(f"Worker {worker.worker_id} timed out")
        _mark_worker_unhealthy(worker.worker_id)
        raise HTTPException(status_code=504, detail="Worker timed out")

    except httpx.HTTPStatusError as e:
        logger.error(f"Worker {worker.worker_id} returned HTTP {e.response.status_code}")
        raise HTTPException(status_code=502, detail=f"Worker error: {e.response.status_code}")

    except httpx.RequestError as e:
        logger.error(f"Could not reach worker {worker.worker_id}: {e}")
        _mark_worker_unhealthy(worker.worker_id)
        raise HTTPException(status_code=502, detail="Worker unreachable")
    finally:
        worker.active_connections -= 1

def _mark_worker_unhealthy(worker_id: str) -> None:
    """Locally mark a worker unhealthy so it's excluded from future routing."""
    if worker_id in ACTIVE_WORKERS:
        ACTIVE_WORKERS[worker_id].healthy = False
        scheduler.update_workers(ACTIVE_WORKERS)
        logger.warning(f"Marked worker {worker_id} as unhealthy")


@app.post("/worker/unhealthy")
async def mark_worker_unhealthy(data: dict):
    """
    Called by the master node or a monitoring system when a worker goes down.
    Immediately removes it from routing without waiting for the next sync.
    """
    worker_id = data.get("worker_id")
    if not worker_id:
        raise HTTPException(status_code=400, detail="worker_id is required")
    if worker_id in ACTIVE_WORKERS:
        _mark_worker_unhealthy(worker_id)
        return {"status": "updated", "worker_id": worker_id}
    return {"status": "not_found", "worker_id": worker_id}

@app.get("/workers")
async def list_workers():
    return {
        "total": len(ACTIVE_WORKERS),
        "healthy": sum(1 for w in ACTIVE_WORKERS.values() if w.healthy),
        "workers": [w.__dict__ for w in ACTIVE_WORKERS.values()],
    }


@app.get("/health")
async def health_check():
    healthy_count = sum(1 for w in ACTIVE_WORKERS.values() if w.healthy)
    return {
        "status": "ok",
        "strategy": STRATEGY,
        "total_workers": len(ACTIVE_WORKERS),
        "healthy_workers": healthy_count,
    }


@app.post("/strategy")
async def set_strategy(body: dict):
    """
    Dynamically switch the default routing strategy at runtime.
    Valid values: round_robin | least_connections | load_aware
    """
    global STRATEGY
    strategy_value = body.get("strategy")
    try:
        STRATEGY = RoutingStrategy(strategy_value)
        logger.info(f"Routing strategy changed to: {STRATEGY}")
        return {"status": "ok", "strategy": STRATEGY}
    except ValueError:
        valid = [s.value for s in RoutingStrategy]
        raise HTTPException(
            status_code=400,
            detail=f"Invalid strategy '{strategy_value}'. Valid: {valid}",
        )

