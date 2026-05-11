import os
import asyncio
import time
import httpx
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from enum import Enum
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(title="GPU Load Balancer")

LB_PORT = int(os.environ.get("LB_PORT", "8000"))
MASTER_URL = os.environ.get("MASTER_NODE_URL", "http://localhost:9000")
HEALTH_CHECK_INTERVAL = 5
MAX_RETRIES = 3
RETRY_DELAY = 0.5

httpx_client: Optional[httpx.AsyncClient] = None


class RoutingStrategy(str, Enum):
    ROUND_ROBIN = "round_robin"
    LEAST_CONNECTIONS = "least_connections"
    HYBRID = "hybrid"
    GPU_AWARE = "gpu_aware"


@dataclass
class WorkerState:
    worker_id: str
    host: str
    port: int
    url: str
    healthy: bool = True
    active_connections: int = 0
    avg_latency_ms: float = 0.0
    gpu_utilization: int = 0
    gpu_memory_mb: int = 0
    last_health_check: float = 0.0
    consecutive_failures: int = 0


@dataclass
class RoutingState:
    round_robin_index: int = 0
    hybrid_rr_index: int = 0
    total_requests: int = 0
    failed_requests: int = 0


workers: Dict[str, WorkerState] = {}
routing_state = RoutingState()
current_strategy: RoutingStrategy = RoutingStrategy.ROUND_ROBIN


class QueryRequest(BaseModel):
    query: str
    user_id: str = ""
    top_k: int = 3


class StrategyRequest(BaseModel):
    strategy: str


async def init_httpx():
    global httpx_client
    limits = httpx.Limits(max_connections=100, max_keepalive_connections=50)
    httpx_client = httpx.AsyncClient(timeout=120.0, limits=limits)


async def close_httpx():
    global httpx_client
    if httpx_client:
        await httpx_client.aclose()


async def check_worker_health(worker: WorkerState) -> bool:
    try:
        resp = await httpx_client.get(f"{worker.url}/health", timeout=5.0)
        if resp.status_code == 200:
            data = resp.json()
            worker.active_connections = data.get("active_connections", 0)
            worker.avg_latency_ms = data.get("avg_latency_ms", 0.0)
            worker.gpu_utilization = data.get("gpu_utilization", 0)
            worker.gpu_memory_mb = data.get("gpu_memory_used_mb", 0)
            worker.last_health_check = time.time()
            worker.consecutive_failures = 0
            return True
    except Exception:
        worker.consecutive_failures += 1
    return False


async def health_check_loop():
    while True:
        await asyncio.sleep(HEALTH_CHECK_INTERVAL)
        for worker in workers.values():
            is_healthy = await check_worker_health(worker)
            if not is_healthy:
                worker.healthy = False
            else:
                worker.healthy = True


def get_healthy_workers() -> List[WorkerState]:
    return [w for w in workers.values() if w.healthy]


def select_round_robin() -> Optional[WorkerState]:
    healthy = get_healthy_workers()
    if not healthy:
        return None
    idx = routing_state.round_robin_index % len(healthy)
    routing_state.round_robin_index += 1
    return healthy[idx]


def select_least_connections() -> Optional[WorkerState]:
    healthy = get_healthy_workers()
    if not healthy:
        return None
    return min(healthy, key=lambda w: w.active_connections)


def select_hybrid() -> Optional[WorkerState]:
    healthy = get_healthy_workers()
    if not healthy:
        return None

    min_connections = min(w.active_connections for w in healthy)
    least_busy = [w for w in healthy if w.active_connections == min_connections]

    if len(least_busy) == 1:
        return least_busy[0]

    idx = routing_state.hybrid_rr_index % len(least_busy)
    routing_state.hybrid_rr_index += 1
    return least_busy[idx]


def select_gpu_aware() -> Optional[WorkerState]:
    healthy = get_healthy_workers()
    if not healthy:
        return None

    available = [w for w in healthy if w.gpu_memory_mb < 5000 and w.gpu_utilization < 80]
    if available:
        return available[0]

    return min(healthy, key=lambda w: (w.gpu_utilization, w.gpu_memory_mb))


def select_worker() -> Optional[WorkerState]:
    if current_strategy == RoutingStrategy.ROUND_ROBIN:
        return select_round_robin()
    elif current_strategy == RoutingStrategy.LEAST_CONNECTIONS:
        return select_least_connections()
    elif current_strategy == RoutingStrategy.HYBRID:
        return select_hybrid()
    elif current_strategy == RoutingStrategy.GPU_AWARE:
        return select_gpu_aware()
    return select_round_robin()


async def forward_to_worker(worker: WorkerState, query: str, top_k: int) -> dict:
    for attempt in range(MAX_RETRIES):
        try:
            resp = await httpx_client.post(
                f"{worker.url}/query",
                json={"query": query, "top_k": top_k},
                timeout=120.0
            )
            if resp.status_code == 200:
                worker.active_connections += 1
                return resp.json()
            elif resp.status_code >= 500 and attempt < MAX_RETRIES - 1:
                await asyncio.sleep(RETRY_DELAY * (attempt + 1))
                continue
            else:
                raise HTTPException(status_code=resp.status_code, detail=resp.text)
        except httpx.TimeoutException:
            if attempt < MAX_RETRIES - 1:
                await asyncio.sleep(RETRY_DELAY * (attempt + 1))
                continue
            raise HTTPException(status_code=504, detail="Worker timeout")
        except Exception as e:
            if attempt < MAX_RETRIES - 1:
                await asyncio.sleep(RETRY_DELAY * (attempt + 1))
                continue
            raise HTTPException(status_code=500, detail=str(e))

    raise HTTPException(status_code=503, detail="All retries failed")


@app.on_event("startup")
async def startup():
    await init_httpx()

    default_workers = [
        ("worker-1", "localhost", 8001),
        ("worker-2", "localhost", 8002),
        ("worker-3", "localhost", 8003),
        ("worker-4", "localhost", 8004),
    ]
    for worker_id, host, port in default_workers:
        workers[worker_id] = WorkerState(
            worker_id=worker_id,
            host=host,
            port=port,
            url=f"http://{host}:{port}"
        )

    asyncio.create_task(health_check_loop())


@app.on_event("shutdown")
async def shutdown():
    await close_httpx()


@app.post("/query")
async def handle_query(request: QueryRequest):
    routing_state.total_requests += 1

    worker = select_worker()
    if not worker:
        routing_state.failed_requests += 1
        raise HTTPException(status_code=503, detail="No healthy workers available")

    try:
        result = await forward_to_worker(worker, request.query, request.top_k)
        worker.active_connections = max(0, worker.active_connections - 1)
        return result
    except Exception as e:
        routing_state.failed_requests += 1
        worker.active_connections = max(0, worker.active_connections - 1)
        raise


@app.post("/worker/unhealthy")
async def mark_worker_unhealthy(data: dict):
    worker_id = data.get("worker_id")
    if worker_id and worker_id in workers:
        workers[worker_id].healthy = False
    return {"status": "ok"}


@app.post("/worker/healthy")
async def mark_worker_healthy(data: dict):
    worker_id = data.get("worker_id")
    if worker_id and worker_id in workers:
        workers[worker_id].healthy = True
        workers[worker_id].consecutive_failures = 0
    return {"status": "ok"}


@app.get("/workers")
async def list_workers():
    return {
        "workers": [
            {
                "worker_id": w.worker_id,
                "host": w.host,
                "port": w.port,
                "healthy": w.healthy,
                "active_connections": w.active_connections,
                "avg_latency_ms": w.avg_latency_ms,
                "gpu_utilization": w.gpu_utilization,
                "gpu_memory_mb": w.gpu_memory_mb,
            }
            for w in workers.values()
        ],
        "strategy": current_strategy.value,
        "total_requests": routing_state.total_requests,
        "failed_requests": routing_state.failed_requests,
    }


@app.get("/strategy")
async def get_strategy():
    return {"strategy": current_strategy.value}


@app.post("/strategy")
async def set_strategy(request: StrategyRequest):
    global current_strategy
    try:
        current_strategy = RoutingStrategy(request.strategy.lower())
        return {"status": "ok", "strategy": current_strategy.value}
    except ValueError:
        valid = [s.value for s in RoutingStrategy]
        raise HTTPException(
            status_code=400,
            detail=f"Invalid strategy. Valid: {valid}"
        )


@app.get("/stats")
async def get_stats():
    healthy = get_healthy_workers()
    return {
        "total_workers": len(workers),
        "healthy_workers": len(healthy),
        "current_strategy": current_strategy.value,
        "total_requests": routing_state.total_requests,
        "failed_requests": routing_state.failed_requests,
        "avg_gpu_utilization": sum(w.gpu_utilization for w in healthy) / len(healthy) if healthy else 0,
        "total_active_connections": sum(w.active_connections for w in workers.values()),
    }


@app.get("/health")
async def health():
    return {"status": "healthy", "strategy": current_strategy.value}


@app.post("/workers/add")
async def add_worker(data: dict):
    worker_id = data.get("worker_id")
    host = data.get("host", "localhost")
    port = data.get("port")

    if not worker_id or not port:
        raise HTTPException(status_code=400, detail="worker_id and port required")

    workers[worker_id] = WorkerState(
        worker_id=worker_id,
        host=host,
        port=port,
        url=f"http://{host}:{port}"
    )
    return {"status": "added", "worker_id": worker_id}


@app.post("/workers/remove")
async def remove_worker(data: dict):
    worker_id = data.get("worker_id")
    if worker_id in workers:
        del workers[worker_id]
    return {"status": "removed", "worker_id": worker_id}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=LB_PORT)