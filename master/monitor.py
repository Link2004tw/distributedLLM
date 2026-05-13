import asyncio
import time
from typing import Dict, List, Optional, Set
from fastapi import FastAPI, HTTPException
import httpx

from common.models import (
    WorkerInfo,
    HealthCheck,
    MetricsSummary,
)

app = FastAPI()

REGISTERED_WORKERS: Dict[str, WorkerInfo] = {}
FAILED_WORKERS: Set[str] = set()
MASTER_PORT = 9000
HEARTBEAT_INTERVAL = 5
FAILURE_THRESHOLD = 3
LOAD_BALANCER_URL = "http://localhost:8000"

# Routing state
_rr_index = 0
_hybrid_rr_index = 0


@app.on_event("startup")
async def startup_event():
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
    if host == "localhost" or host == "127.0.0.1":
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
                        worker.avg_latency_ms = data.get("avg_latency_ms", 0.0)
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


@app.post("/register")
async def register(data: dict):
    worker_id = data.get("worker_id")
    port = data.get("port")
    host = data.get("host", "localhost")
    await register_worker(worker_id, port, host)
    return {"status": "registered", "worker_id": worker_id}


@app.get("/workers")
async def list_workers():
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
    return {"status": "ok", "workers": len(REGISTERED_WORKERS)}


@app.delete("/worker/{worker_id}")
async def remove_worker(worker_id: str):
    if worker_id in REGISTERED_WORKERS:
        del REGISTERED_WORKERS[worker_id]
        return {"status": "removed"}
    raise HTTPException(status_code=404, detail="Worker not found")


def get_healthy_workers() -> List[WorkerInfo]:
    return [w for w in REGISTERED_WORKERS.values() if w.healthy]


def select_round_robin(exclude: Set[str] = None) -> Optional[WorkerInfo]:
    global _rr_index
    healthy = [w for w in get_healthy_workers() if not exclude or w.worker_id not in exclude]
    if not healthy:
        return None
    idx = _rr_index % len(healthy)
    _rr_index += 1
    return healthy[idx]


def select_least_connections(exclude: Set[str] = None) -> Optional[WorkerInfo]:
    healthy = [w for w in get_healthy_workers() if not exclude or w.worker_id not in exclude]
    if not healthy:
        return None
    return min(healthy, key=lambda w: w.active_connections)


def select_hybrid(exclude: Set[str] = None) -> Optional[WorkerInfo]:
    global _hybrid_rr_index
    healthy = [w for w in get_healthy_workers() if not exclude or w.worker_id not in exclude]
    if not healthy:
        return None
    min_conn = min(w.active_connections for w in healthy)
    least_busy = [w for w in healthy if w.active_connections == min_conn]
    if len(least_busy) == 1:
        return least_busy[0]
    idx = _hybrid_rr_index % len(least_busy)
    _hybrid_rr_index += 1
    return least_busy[idx]


def select_load_aware(exclude: Set[str] = None) -> Optional[WorkerInfo]:
    healthy = [w for w in get_healthy_workers() if not exclude or w.worker_id not in exclude]
    if not healthy:
        return None
    def score(w):
        return w.active_connections * 30 + w.avg_latency_ms * 10
    return min(healthy, key=score)


def select_gpu_aware(exclude: Set[str] = None) -> Optional[WorkerInfo]:
    healthy = [w for w in get_healthy_workers() if not exclude or w.worker_id not in exclude]
    if not healthy:
        return None
    def score(w):
        return w.active_connections * 10 + w.avg_latency_ms * 5
    return min(healthy, key=score)


def select_worker(strategy: str = "round_robin", exclude: Set[str] = None) -> Optional[WorkerInfo]:
    if strategy == "least_connections":
        return select_least_connections(exclude)
    elif strategy == "load_aware":
        return select_load_aware(exclude)
    elif strategy == "gpu_aware":
        return select_gpu_aware(exclude)
    elif strategy == "hybrid":
        return select_hybrid(exclude)
    return select_round_robin(exclude)


@app.post("/schedule")
async def schedule(data: dict):
    strategy = data.get("strategy", "round_robin")
    exclude = set(data.get("exclude_workers", []))
    worker = select_worker(strategy, exclude)
    if not worker:
        raise HTTPException(status_code=503, detail="No healthy workers available")
    return {
        "worker_id": worker.worker_id,
        "host": worker.host,
        "port": worker.port,
        "url": f"http://{worker.host}:{worker.port}",
    }


@app.post("/routing/reset")
async def reset_routing():
    global _rr_index, _hybrid_rr_index
    _rr_index = 0
    _hybrid_rr_index = 0
    return {"status": "reset"}
