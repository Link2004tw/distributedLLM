import os
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import httpx
from lb.load_balancer import LoadBalancer

app = FastAPI(title="Load Balancer")
try:
    lb = LoadBalancer()
except Exception:
    lb = None

LB_STRATEGY = os.environ.get("LB_STRATEGY", "round_robin")


class QueryRequest(BaseModel):
    query: str
    user_id: str = ""
    top_k: int = 3


class StrategyRequest(BaseModel):
    strategy: str


@app.post("/query")
async def query_worker(req: QueryRequest):
    if lb is not None:
        worker = lb.get_next_server(LB_STRATEGY)
        if worker:
            try:
                async with httpx.AsyncClient(timeout=60.0) as client:
                    resp = await client.post(
                        f"http://localhost:{worker['port']}/query",
                        json=req.model_dump(),
                    )
                    if resp.status_code == 200:
                        return resp.json()
            except Exception:
                pass
    for port in [8001, 8002, 8003, 8004]:
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post(
                    f"http://localhost:{port}/query",
                    json=req.model_dump(),
                )
                if resp.status_code == 200:
                    return resp.json()
        except Exception:
            continue
    raise HTTPException(status_code=503, detail="No healthy workers available")


@app.post("/worker/unhealthy")
async def worker_unhealthy(data: dict):
    worker_id = data.get("worker_id", "unknown")
    if lb is not None:
        try:
            lb.disable_worker(worker_id)
        except Exception:
            pass
    return {"status": "disabled", "worker_id": worker_id}


@app.post("/worker/{worker_id}/disable")
async def disable_worker(worker_id: str):
    if lb is None:
        raise HTTPException(status_code=503, detail="NGINX not available")
    lb.disable_worker(worker_id)
    return {"status": "disabled", "worker_id": worker_id}


@app.post("/worker/{worker_id}/enable")
async def enable_worker(worker_id: str):
    if lb is None:
        raise HTTPException(status_code=503, detail="NGINX not available")
    lb.enable_worker(worker_id)
    return {"status": "enabled", "worker_id": worker_id}


@app.get("/strategy")
async def get_strategy():
    if lb is None:
        raise HTTPException(status_code=503, detail="NGINX not available")
    return {"strategy": lb.get_current_strategy()}


@app.post("/strategy")
async def set_strategy(req: StrategyRequest):
    if lb is None:
        raise HTTPException(status_code=503, detail="NGINX not available")
    try:
        lb.switch_strategy(req.strategy)
        return {"strategy": lb.get_current_strategy()}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/workers")
async def get_workers():
    if lb is None:
        raise HTTPException(status_code=503, detail="NGINX not available")
    return {"workers": lb.get_worker_list()}


@app.get("/status")
async def get_status():
    if lb is None:
        raise HTTPException(status_code=503, detail="NGINX not available")
    return lb.get_status()


@app.get("/health")
async def health():
    return {"status": "ok", "service": "lb-controller"}
