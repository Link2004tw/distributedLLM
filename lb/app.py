from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from lb.load_balancer import LoadBalancer

app = FastAPI(title="NGINX Load Balancer Controller")
lb = LoadBalancer()


class StrategyRequest(BaseModel):
    strategy: str


@app.post("/worker/{worker_id}/disable")
async def disable_worker(worker_id: str):
    try:
        lb.disable_worker(worker_id)
        return {"status": "disabled", "worker_id": worker_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/worker/{worker_id}/enable")
async def enable_worker(worker_id: str):
    try:
        lb.enable_worker(worker_id)
        return {"status": "enabled", "worker_id": worker_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/strategy")
async def get_strategy():
    return {"strategy": lb.get_current_strategy()}


@app.post("/strategy")
async def set_strategy(req: StrategyRequest):
    try:
        lb.switch_strategy(req.strategy)
        return {"strategy": lb.get_current_strategy()}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.get("/workers")
async def get_workers():
    return {"workers": lb.get_worker_list()}


@app.get("/status")
async def get_status():
    return lb.get_status()


@app.get("/health")
async def health():
    return {"status": "ok", "service": "lb-controller"}
