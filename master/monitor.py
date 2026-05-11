import os
import asyncio
import logging
import time
from typing import Dict, List, Set
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import httpx

from common.models import (
    WorkerInfo,
    HealthCheck,
    MetricsSummary,
)

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("master")

app = FastAPI(title="Master Node")

REGISTERED_WORKERS: Dict[str, WorkerInfo] = {}
FAILED_WORKERS: Set[str] = set()
MASTER_PORT = 9000
HEARTBEAT_INTERVAL = 5
FAILURE_THRESHOLD = 3
LOAD_BALANCER_URL = "http://localhost:8000"

WORKER_URLS_RAW = os.environ.get("WORKER_URLS", "")
WORKER_URLS_LIST: List[str] = [u.strip() for u in WORKER_URLS_RAW.split(",") if u.strip()]
rr_index = 0


class QueryRequest(BaseModel):
    query: str
    top_k: int = 3


@app.on_event("startup")
async def startup_event():
    if WORKER_URLS_LIST:
        logger.info("Distributed mode: configured %d workers via WORKER_URLS", len(WORKER_URLS_LIST))
        for u in WORKER_URLS_LIST:
            logger.info("  worker: %s", u)
    asyncio.create_task(heartbeat_monitor())


async def register_worker(worker_id: str, port: int, host: str = "localhost"):
    REGISTERED_WORKERS[worker_id] = WorkerInfo(
        worker_id=worker_id,
        port=port,
        host=host,
        healthy=True,
        active_connections=0,
        avg_latency_ms=0.0,
        last_heartbeat=time.time(),
    )
    asyncio.create_task(notify_load_balancer_worker_added(worker_id, host, port))


async def heartbeat_monitor():
    while True:
        await asyncio.sleep(HEARTBEAT_INTERVAL)
        for worker_id, worker in list(REGISTERED_WORKERS.items()):
            try:
                async with httpx.AsyncClient(timeout=3.0) as client:
                    response = await client.get(
                        f"http://{worker.host}:{worker.port}/health"
                    )
                    if response.status_code == 200:
                        data = response.json()
                        worker.healthy = data.get("healthy", True)
                        worker.active_connections = data.get("active_connections", 0)
                        worker.last_heartbeat = time.time()
            except Exception:
                worker.healthy = False

            if not worker.healthy:
                FAILED_WORKERS.add(worker_id)
                if len(FAILED_WORKERS) >= FAILURE_THRESHOLD:
                    await notify_load_balancer(worker_id)


async def notify_load_balancer(worker_id: str):
    try:
        async with httpx.AsyncClient() as client:
            await client.post(
                f"{LOAD_BALANCER_URL}/worker/unhealthy", json={"worker_id": worker_id}
            )
    except Exception:
        pass


async def notify_load_balancer_worker_added(worker_id: str, host: str, port: int):
    try:
        async with httpx.AsyncClient() as client:
            await client.post(
                f"{LOAD_BALANCER_URL}/workers/add",
                json={"worker_id": worker_id, "host": host, "port": port}
            )
    except Exception:
        pass


@app.post("/query")
async def handle_query(request: QueryRequest):
    global rr_index

    urls = WORKER_URLS_LIST
    if not urls:
        raise HTTPException(status_code=500, detail="No workers configured via WORKER_URLS")

    num_workers = len(urls)
    errors = []

    for i in range(num_workers):
        idx = (rr_index + i) % num_workers
        worker_url = urls[idx]
        logger.info("Selected worker %d: %s", idx, worker_url)

        async with httpx.AsyncClient(timeout=120.0) as client:
            try:
                resp = await client.post(worker_url, json=request.model_dump())
                if resp.status_code == 200:
                    rr_index = (idx + 1) % num_workers
                    logger.info("Worker %s succeeded", worker_url)
                    return resp.json()
                else:
                    msg = f"Worker {worker_url} returned status {resp.status_code}"
                    logger.warning(msg)
                    errors.append(msg)
            except httpx.TimeoutException:
                msg = f"Worker {worker_url} timed out"
                logger.error(msg)
                errors.append(msg)
            except Exception as e:
                msg = f"Worker {worker_url} failed: {str(e)}"
                logger.error(msg)
                errors.append(msg)

    raise HTTPException(
        status_code=503,
        detail=f"All workers failed: {'; '.join(errors)}"
    )


@app.post("/register")
async def register(data: dict):
    worker_id = data.get("worker_id")
    port = data.get("port")
    host = data.get("host", "localhost")
    await register_worker(worker_id, port, host)
    return {"status": "registered", "worker_id": worker_id}


@app.get("/workers")
async def list_workers():
    if WORKER_URLS_LIST:
        return {"workers": WORKER_URLS_LIST, "count": len(WORKER_URLS_LIST)}
    return {
        "workers": [
            {
                "worker_id": w.worker_id,
                "port": w.port,
                "host": w.host,
                "healthy": w.healthy,
                "active_connections": w.active_connections,
                "avg_latency_ms": w.avg_latency_ms,
                "last_heartbeat": w.last_heartbeat,
            }
            for w in REGISTERED_WORKERS.values()
        ]
    }


@app.get("/metrics")
async def get_metrics():
    total_requests = sum(w.active_connections for w in REGISTERED_WORKERS.values())
    avg_latency = (
        sum(w.avg_latency_ms for w in REGISTERED_WORKERS.values()) / len(REGISTERED_WORKERS)
        if REGISTERED_WORKERS
        else 0.0
    )
    return MetricsSummary(
        total_requests=total_requests,
        avg_latency_ms=avg_latency,
        failed_workers=len(FAILED_WORKERS),
        worker_stats={w.worker_id: w.active_connections for w in REGISTERED_WORKERS.values()},
    )


@app.get("/health")
async def health_check():
    workers_count = len(WORKER_URLS_LIST) if WORKER_URLS_LIST else len(REGISTERED_WORKERS)
    return {"status": "ok", "role": "master", "workers_count": workers_count}


@app.delete("/worker/{worker_id}")
async def remove_worker(worker_id: str):
    if worker_id in REGISTERED_WORKERS:
        del REGISTERED_WORKERS[worker_id]
        return {"status": "removed"}
    raise HTTPException(status_code=404, detail="Worker not found")
