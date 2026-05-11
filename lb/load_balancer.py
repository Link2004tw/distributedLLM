import time
import httpx
from typing import Dict, List, Optional
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel
import asyncio
from common.models import RoutingStrategy

app = FastAPI()

class StrategyRequest(BaseModel):
    strategy: str

class QueryRequest(BaseModel):
    id: Optional[str] = None
    request_id: Optional[str] = None
    client_id: Optional[int] = None
    query: str
    top_k: Optional[int] = 3

class WorkerRegistry:
    def __init__(self):
        self.workers: Dict[str, dict] = {
            "worker-1": {"host": "127.0.0.1", "port": 8001, "healthy": True, "active_connections": 0},
            "worker-2": {"host": "127.0.0.1", "port": 8002, "healthy": True, "active_connections": 0},
            "worker-3": {"host": "127.0.0.1", "port": 8003, "healthy": True, "active_connections": 0},
            "worker-4": {"host": "127.0.0.1", "port": 8004, "healthy": True, "active_connections": 0},
        }
        self.strategy = RoutingStrategy.ROUND_ROBIN
        self.round_robin_index = 0
        self.lock = asyncio.Lock()
        
        self.start_time = time.time()
        self.total_requests = 0
        self.successful_requests = 0
        self.failed_requests = 0
        self.total_latency_ms = 0.0

    async def get_worker(self) -> Optional[str]:
        async with self.lock:
            healthy_workers = [w for w, data in self.workers.items() if data["healthy"]]
            if not healthy_workers:
                return None

            if self.strategy == RoutingStrategy.ROUND_ROBIN:
                worker_id = healthy_workers[self.round_robin_index % len(healthy_workers)]
                self.round_robin_index += 1
                return worker_id
            elif self.strategy == RoutingStrategy.LEAST_CONNECTIONS:
                worker_id = min(healthy_workers, key=lambda w: self.workers[w]["active_connections"])
                return worker_id
            else:
                worker_id = healthy_workers[self.round_robin_index % len(healthy_workers)]
                self.round_robin_index += 1
                return worker_id

    async def increment_connections(self, worker_id: str):
        async with self.lock:
            if worker_id in self.workers:
                self.workers[worker_id]["active_connections"] += 1

    async def decrement_connections(self, worker_id: str):
        async with self.lock:
            if worker_id in self.workers:
                self.workers[worker_id]["active_connections"] = max(0, self.workers[worker_id]["active_connections"] - 1)

    async def record_metrics(self, success: bool, latency_ms: float = 0.0):
        async with self.lock:
            self.total_requests += 1
            if success:
                self.successful_requests += 1
                self.total_latency_ms += latency_ms
            else:
                self.failed_requests += 1

registry = WorkerRegistry()

timeout_config = httpx.Timeout(60.0, connect=10.0)
client = httpx.AsyncClient(timeout=timeout_config)

@app.on_event("shutdown")
async def shutdown_event():
    await client.aclose()

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.get("/workers")
async def get_workers():
    return {
        "workers": [
            {
                "id": w_id,
                "host": data["host"],
                "port": data["port"],
                "status": "healthy" if data["healthy"] else "unhealthy",
                "active_connections": data["active_connections"]
            }
            for w_id, data in registry.workers.items()
        ]
    }

class WorkerRegistration(BaseModel):
    worker_id: str
    host: str = "127.0.0.1"
    port: int

@app.post("/workers/register")
async def register_worker(reg: WorkerRegistration):
    async with registry.lock:
        registry.workers[reg.worker_id] = {
            "host": reg.host,
            "port": reg.port,
            "healthy": True,
            "active_connections": 0
        }
    return {"status": "success"}

class WorkerUnhealthy(BaseModel):
    worker_id: str

@app.post("/worker/unhealthy")
async def mark_unhealthy(req: WorkerUnhealthy):
    async with registry.lock:
        if req.worker_id in registry.workers:
            registry.workers[req.worker_id]["healthy"] = False
    return {"status": "success"}

@app.post("/worker/healthy")
async def mark_healthy(req: WorkerUnhealthy):
    async with registry.lock:
        if req.worker_id in registry.workers:
            registry.workers[req.worker_id]["healthy"] = True
    return {"status": "success"}

@app.get("/strategy")
async def get_strategy():
    return {"strategy": registry.strategy.value}

@app.post("/strategy")
async def set_strategy(req: StrategyRequest):
    try:
        strategy = RoutingStrategy(req.strategy)
        registry.strategy = strategy
        return {"status": "success", "strategy": strategy.value}
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid strategy")

@app.get("/metrics")
async def get_metrics():
    uptime = time.time() - registry.start_time
    avg_latency = registry.total_latency_ms / registry.successful_requests if registry.successful_requests > 0 else 0
    throughput = registry.total_requests / uptime if uptime > 0 else 0
    
    active_conns = sum(w["active_connections"] for w in registry.workers.values())
    
    return {
      "total_requests": registry.total_requests,
      "successful_requests": registry.successful_requests,
      "failed_requests": registry.failed_requests,
      "average_latency_ms": avg_latency,
      "p50_latency_ms": avg_latency,
      "p95_latency_ms": avg_latency,
      "p99_latency_ms": avg_latency,
      "throughput_rps": throughput,
      "active_connections": active_conns
    }

@app.post("/query")
async def proxy_query(req: Request):
    body = await req.json()
    
    retries = 3
    for attempt in range(retries):
        worker_id = await registry.get_worker()
        if not worker_id:
            await registry.record_metrics(success=False)
            raise HTTPException(status_code=503, detail="No healthy workers available")
            
        worker = registry.workers[worker_id]
        url = f"http://{worker['host']}:{worker['port']}/query"
        
        await registry.increment_connections(worker_id)
        start_time = time.time()
        try:
            with open("lb_log.txt", "a") as f:
                f.write(f"[LB] Forwarding request to {worker_id} at {url} (Attempt {attempt + 1})\n")
            response = await client.post(url, json=body)
            if response.status_code >= 500:
                with open("lb_log.txt", "a") as f:
                    f.write(f"[LB] {worker_id} returned 5xx status: {response.status_code}\n")
                continue
                
            latency_ms = (time.time() - start_time) * 1000
            await registry.record_metrics(success=True, latency_ms=latency_ms)
            
            data = response.json()
            if data.get("status") == "fallback":
                with open("lb_log.txt", "a") as f:
                    f.write(f"[LB] {worker_id} returned fallback response, treating as success.\n")
            
            return data
        except httpx.RequestError as e:
            with open("lb_log.txt", "a") as f:
                f.write(f"[LB] RequestError to {worker_id}: {str(e)} ({type(e).__name__})\n")
            continue
        except Exception as e:
            with open("lb_log.txt", "a") as f:
                f.write(f"[LB] Exception to {worker_id}: {str(e)} ({type(e).__name__})\n")
            continue
        finally:
            await registry.decrement_connections(worker_id)
            
    await registry.record_metrics(success=False)
    raise HTTPException(status_code=502, detail="All retries failed")
