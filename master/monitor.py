import asyncio
import time
from typing import Dict, Set
from fastapi import FastAPI
import httpx
from pydantic import BaseModel

app = FastAPI()

class WorkerInfo(BaseModel):
    worker_id: str
    port: int
    host: str
    healthy: bool = True
    active_connections: int = 0
    avg_latency_ms: float = 0.0
    last_heartbeat: float = 0.0
    missed_heartbeats: int = 0

REGISTERED_WORKERS: Dict[str, WorkerInfo] = {}
MASTER_PORT = 9000
HEARTBEAT_INTERVAL = 5
FAILURE_THRESHOLD = 3
LOAD_BALANCER_URL = "http://127.0.0.1:8000"

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(heartbeat_monitor())

async def register_worker(worker_id: str, port: int, host: str = "127.0.0.1"):
    REGISTERED_WORKERS[worker_id] = WorkerInfo(
        worker_id=worker_id,
        port=port,
        host=host,
        healthy=True,
        active_connections=0,
        avg_latency_ms=0.0,
        last_heartbeat=time.time(),
        missed_heartbeats=0,
    )

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
                        if not worker.healthy:
                            worker.healthy = True
                            await notify_load_balancer_healthy(worker_id)
                        worker.missed_heartbeats = 0
                        worker.last_heartbeat = time.time()
                    else:
                        worker.missed_heartbeats += 1
            except Exception:
                worker.missed_heartbeats += 1

            if worker.missed_heartbeats >= FAILURE_THRESHOLD and worker.healthy:
                worker.healthy = False
                await notify_load_balancer(worker_id)

async def notify_load_balancer(worker_id: str):
    try:
        async with httpx.AsyncClient() as client:
            await client.post(
                f"{LOAD_BALANCER_URL}/worker/unhealthy", json={"worker_id": worker_id}
            )
    except Exception:
        pass

async def notify_load_balancer_healthy(worker_id: str):
    try:
        async with httpx.AsyncClient() as client:
            await client.post(
                f"{LOAD_BALANCER_URL}/worker/healthy", json={"worker_id": worker_id}
            )
    except Exception:
        pass

@app.post("/workers/register")
async def register(data: dict):
    worker_id = data.get("worker_id")
    port = data.get("port")
    host = data.get("host", "127.0.0.1")
    await register_worker(worker_id, port, host)
    return {"status": "registered", "worker_id": worker_id}

@app.get("/workers")
async def list_workers():
    return {
        "workers": [
            {
                "id": w.worker_id,
                "host": w.host,
                "port": w.port,
                "status": "healthy" if w.healthy else "unhealthy",
                "active_connections": w.active_connections,
                "latency_ms": w.avg_latency_ms,
                "last_heartbeat": str(w.last_heartbeat),
            }
            for w in REGISTERED_WORKERS.values()
        ]
    }

@app.get("/metrics")
async def get_metrics():
    active_conns = sum(w.active_connections for w in REGISTERED_WORKERS.values())
    avg_latency = (
        sum(w.avg_latency_ms for w in REGISTERED_WORKERS.values()) / len(REGISTERED_WORKERS)
        if REGISTERED_WORKERS
        else 0.0
    )
    return {
      "total_requests": active_conns,
      "successful_requests": 0,
      "failed_requests": 0,
      "average_latency_ms": avg_latency,
      "p50_latency_ms": avg_latency,
      "p95_latency_ms": avg_latency,
      "p99_latency_ms": avg_latency,
      "throughput_rps": 0,
      "active_connections": active_conns
    }

@app.get("/health")
async def health_check():
    return {"status": "ok", "workers": len(REGISTERED_WORKERS)}