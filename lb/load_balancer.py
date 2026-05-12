import os
import asyncio
import time
import json
import httpx
from pathlib import Path
from typing import Dict, List, Optional, Set
from dataclasses import dataclass, field, asdict
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
    LOAD_AWARE = "load_aware"
    GPU_AWARE = "gpu_aware"
    HYBRID = "hybrid"


@dataclass
class WorkerState:
    worker_id: str
    host: str
    port: int
    url: str
    healthy: bool = True
    active_connections: int = 0
    queue_available: int = 50
    avg_latency_ms: float = 0.0
    gpu_utilization: int = 0
    gpu_memory_mb: int = 0
    last_health_check: float = 0.0
    consecutive_failures: int = 0


MAX_CONSECUTIVE_FAILURES = 3


@dataclass
class RoutingState:
    round_robin_index: int = 0
    hybrid_rr_index: int = 0
    total_requests: int = 0
    failed_requests: int = 0
    reassigned_requests: int = 0
    successful_requests: int = 0
    request_latencies: deque = field(default_factory=lambda: deque(maxlen=1000))
    per_worker_throughput: Dict[str, int] = field(default_factory=dict)


@dataclass
class FailedRequest:
    query: str
    top_k: int
    attempts: int = 0
    failed_workers: Set[str] = field(default_factory=set)


workers: Dict[str, WorkerState] = {}
routing_state = RoutingState()
current_strategy: RoutingStrategy = RoutingStrategy.ROUND_ROBIN
pending_requests: List[FailedRequest] = []
MAX_REASSIGN_ATTEMPTS = 3
MAX_CONCURRENT_REQUESTS = 50
request_semaphore: Optional[asyncio.Semaphore] = None

PERSISTENCE_FILE = Path(os.environ.get("PENDING_REQUESTS_FILE", "./pending_requests.json"))


def save_pending_requests():
    try:
        data = {
            "requests": [
                {
                    "query": r.query,
                    "top_k": r.top_k,
                    "attempts": r.attempts,
                    "failed_workers": list(r.failed_workers)
                }
                for r in pending_requests
            ],
            "timestamp": time.time()
        }
        with open(PERSISTENCE_FILE, "w") as f:
            json.dump(data, f)
    except Exception as e:
        print(f"Failed to save pending requests: {e}")


def load_pending_requests():
    global pending_requests
    if not PERSISTENCE_FILE.exists():
        return

    try:
        with open(PERSISTENCE_FILE, "r") as f:
            data = json.load(f)

        requests = []
        for r in data.get("requests", []):
            requests.append(FailedRequest(
                query=r["query"],
                top_k=r["top_k"],
                attempts=r.get("attempts", 0),
                failed_workers=set(r.get("failed_workers", []))
            ))

        if requests:
            pending_requests = requests
            print(f"Loaded {len(requests)} pending requests from disk")
    except Exception as e:
        print(f"Failed to load pending requests: {e}")


def clear_persistent_requests():
    try:
        if PERSISTENCE_FILE.exists():
            PERSISTENCE_FILE.unlink()
    except Exception:
        pass


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
            worker.queue_available = data.get("queue_available", 50)
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

    def gpu_score(w: WorkerState) -> float:
        util = w.gpu_utilization
        mem = w.gpu_memory_mb
        conn = w.active_connections
        queue = max(1, w.queue_available)

        mem_ratio = mem / max(w.gpu_memory_mb, 1)
        conn_factor = conn * 10
        queue_factor = (100 - queue) * 2

        return util + (mem_ratio * 50) + conn_factor + queue_factor

    return min(healthy, key=gpu_score)


def select_load_aware() -> Optional[WorkerState]:
    healthy = get_healthy_workers()
    if not healthy:
        return None

    def load_score(w: WorkerState) -> float:
        conn_score = w.active_connections * 30
        latency_score = w.avg_latency_ms * 10
        queue_penalty = max(0, 50 - w.queue_available) * 5
        gpu_penalty = w.gpu_utilization * 5
        return conn_score + latency_score + queue_penalty + gpu_penalty

    return min(healthy, key=load_score)


def select_worker() -> Optional[WorkerState]:
    if current_strategy == RoutingStrategy.ROUND_ROBIN:
        return select_round_robin()
    elif current_strategy == RoutingStrategy.LEAST_CONNECTIONS:
        return select_least_connections()
    elif current_strategy == RoutingStrategy.LOAD_AWARE:
        return select_load_aware()
    elif current_strategy == RoutingStrategy.GPU_AWARE:
        return select_gpu_aware()
    elif current_strategy == RoutingStrategy.HYBRID:
        return select_hybrid()
    return select_round_robin()


def mark_worker_unhealthy(worker_id: str):
    if worker_id in workers:
        workers[worker_id].healthy = False
        asyncio.create_task(reassign_pending_requests())


async def reassign_pending_requests():
    global pending_requests
    if not pending_requests:
        return

    still_pending = []
    for req in pending_requests:
        healthy = [w for w in workers.values() if w.healthy and w.worker_id not in req.failed_workers]
        if not healthy:
            still_pending.append(req)
            continue

        if current_strategy == RoutingStrategy.ROUND_ROBIN:
            idx = routing_state.round_robin_index % len(healthy)
            routing_state.round_robin_index += 1
            worker = healthy[idx]
        elif current_strategy == RoutingStrategy.LEAST_CONNECTIONS:
            worker = min(healthy, key=lambda w: w.active_connections)
        elif current_strategy == RoutingStrategy.HYBRID:
            min_conn = min(w.active_connections for w in healthy)
            least_busy = [w for w in healthy if w.active_connections == min_conn]
            idx = routing_state.hybrid_rr_index % len(least_busy)
            routing_state.hybrid_rr_index += 1
            worker = least_busy[idx]
        elif current_strategy == RoutingStrategy.GPU_AWARE:
            def gpu_score(w: WorkerState) -> float:
                util = w.gpu_utilization
                mem = w.gpu_memory_mb
                conn = w.active_connections
                mem_ratio = mem / max(w.gpu_memory_mb, 1)
                return util + (mem_ratio * 50) + (conn * 10)
            worker = min(healthy, key=gpu_score)
        elif current_strategy == RoutingStrategy.LOAD_AWARE:
            worker = min(healthy, key=lambda w: w.active_connections * 30 + w.avg_latency_ms * 10 + max(0, 50 - w.queue_available) * 5 + w.gpu_utilization * 5)
        else:
            worker = healthy[0]

        try:
            resp = await httpx_client.post(
                f"{worker.url}/query",
                json={"query": req.query, "top_k": req.top_k},
                timeout=60.0
            )
            if resp.status_code == 200:
                routing_state.reassigned_requests += 1
                continue
        except Exception:
            pass

        req.attempts += 1
        req.failed_workers.add(worker.worker_id)
        if req.attempts < MAX_REASSIGN_ATTEMPTS:
            still_pending.append(req)

    pending_requests = still_pending
    save_pending_requests()


async def forward_to_worker(worker: WorkerState, query: str, top_k: int, exclude_workers: Set[str] = None) -> dict:
    exclude_set = exclude_workers or set()
    last_error = None

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
                last_error = HTTPException(status_code=resp.status_code, detail=resp.text)
        except httpx.TimeoutException:
            last_error = HTTPException(status_code=504, detail="Worker timeout")
            if attempt < MAX_RETRIES - 1:
                await asyncio.sleep(RETRY_DELAY * (attempt + 1))
                continue
        except Exception as e:
            last_error = e
            if attempt < MAX_RETRIES - 1:
                await asyncio.sleep(RETRY_DELAY * (attempt + 1))
                continue

    worker.consecutive_failures += 1
    if worker.consecutive_failures >= MAX_CONSECUTIVE_FAILURES:
        mark_worker_unhealthy(worker.worker_id)

    healthy = [w for w in workers.values() if w.healthy and w.worker_id not in exclude_set]
    if healthy:
        if current_strategy == RoutingStrategy.ROUND_ROBIN:
            idx = routing_state.round_robin_index % len(healthy)
            routing_state.round_robin_index += 1
            alt_worker = healthy[idx]
        elif current_strategy == RoutingStrategy.LEAST_CONNECTIONS:
            alt_worker = min(healthy, key=lambda w: w.active_connections)
        elif current_strategy == RoutingStrategy.HYBRID:
            min_conn = min(w.active_connections for w in healthy)
            least_busy = [w for w in healthy if w.active_connections == min_conn]
            idx = routing_state.hybrid_rr_index % len(least_busy)
            routing_state.hybrid_rr_index += 1
            alt_worker = least_busy[idx]
        elif current_strategy == RoutingStrategy.GPU_AWARE:
            def gpu_score(w: WorkerState) -> float:
                util = w.gpu_utilization
                mem = w.gpu_memory_mb
                conn = w.active_connections
                mem_ratio = mem / max(w.gpu_memory_mb, 1)
                return util + (mem_ratio * 50) + (conn * 10)
            alt_worker = min(healthy, key=gpu_score)
        elif current_strategy == RoutingStrategy.LOAD_AWARE:
            alt_worker = min(healthy, key=lambda w: w.active_connections * 30 + w.avg_latency_ms * 10 + max(0, 50 - w.queue_available) * 5 + w.gpu_utilization * 5)
        else:
            alt_worker = healthy[0]

        exclude_set.add(worker.worker_id)
        try:
            return await forward_to_worker(alt_worker, query, top_k, exclude_set)
        except Exception:
            pass

    pending_requests.append(FailedRequest(query=query, top_k=top_k, attempts=1, failed_workers=exclude_set))
    save_pending_requests()
    if last_error and isinstance(last_error, HTTPException):
        raise last_error
    raise HTTPException(status_code=503, detail="All retries and reassignments failed")


@app.on_event("startup")
async def startup():
    global request_semaphore
    await init_httpx()
    request_semaphore = asyncio.Semaphore(MAX_CONCURRENT_REQUESTS)

    load_pending_requests()

    default_workers = []
    for i in range(1, 5):
        host = os.environ.get(f"WORKER{i}", "localhost")
        port = int(os.environ.get(f"WORKER{i}_PORT", f"800{i}"))
        default_workers.append((f"worker-{i}", host, port))
    for worker_id, host, port in default_workers:
        workers[worker_id] = WorkerState(
            worker_id=worker_id,
            host=host,
            port=port,
            url=f"http://{host}:{port}"
        )

    asyncio.create_task(health_check_loop())
    asyncio.create_task(pending_retry_loop())


@app.on_event("shutdown")
async def shutdown():
    save_pending_requests()
    await close_httpx()


@app.post("/query")
async def handle_query(request: QueryRequest):
    import time
    routing_state.total_requests += 1
    start_time = time.time()

    worker = select_worker()
    if not worker:
        routing_state.failed_requests += 1
        raise HTTPException(status_code=503, detail="No healthy workers available")

    try:
        async with request_semaphore:
            result = await forward_to_worker(worker, request.query, request.top_k)

        latency_ms = (time.time() - start_time) * 1000
        routing_state.request_latencies.append(latency_ms)
        routing_state.successful_requests += 1

        if worker.worker_id not in routing_state.per_worker_throughput:
            routing_state.per_worker_throughput[worker.worker_id] = 0
        routing_state.per_worker_throughput[worker.worker_id] += 1

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


def calculate_percentile(values: List[float], percentile: float) -> float:
    if not values:
        return 0.0
    sorted_vals = sorted(values)
    idx = int((percentile / 100) * len(sorted_vals))
    idx = min(idx, len(sorted_vals) - 1)
    return round(sorted_vals[max(0, idx)], 2)


@app.get("/stats")
async def get_stats():
    healthy = get_healthy_workers()
    latencies = list(routing_state.request_latencies)

    return {
        "total_workers": len(workers),
        "healthy_workers": len(healthy),
        "current_strategy": current_strategy.value,
        "total_requests": routing_state.total_requests,
        "successful_requests": routing_state.successful_requests,
        "failed_requests": routing_state.failed_requests,
        "reassigned_requests": routing_state.reassigned_requests,
        "pending_requests": len(pending_requests),
        "error_rate_percent": round((routing_state.failed_requests / routing_state.total_requests * 100), 2) if routing_state.total_requests > 0 else 0,
        "avg_gpu_utilization": sum(w.gpu_utilization for w in healthy) / len(healthy) if healthy else 0,
        "total_active_connections": sum(w.active_connections for w in workers.values()),
        "latency": {
            "count": len(latencies),
            "avg_ms": round(sum(latencies) / len(latencies), 2) if latencies else 0,
            "min_ms": round(min(latencies), 2) if latencies else 0,
            "max_ms": round(max(latencies), 2) if latencies else 0,
            "p50_ms": calculate_percentile(latencies, 50),
            "p75_ms": calculate_percentile(latencies, 75),
            "p90_ms": calculate_percentile(latencies, 90),
            "p95_ms": calculate_percentile(latencies, 95),
            "p99_ms": calculate_percentile(latencies, 99),
        },
        "per_worker_throughput": dict(routing_state.per_worker_throughput),
    }


async def pending_retry_loop():
    while True:
        await asyncio.sleep(5)
        if pending_requests:
            await reassign_pending_requests()


@app.get("/health")
async def health():
    return {"status": "healthy", "strategy": current_strategy.value}


@app.post("/pending/clear")
async def clear_pending():
    global pending_requests
    pending_requests = []
    clear_persistent_requests()
    return {"status": "ok", "message": "Pending requests cleared"}


@app.get("/pending/count")
async def get_pending_count():
    return {"count": len(pending_requests), "persistence_file": str(PERSISTENCE_FILE)}


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