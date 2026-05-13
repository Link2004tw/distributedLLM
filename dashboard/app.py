import os
import time
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
import httpx

app = FastAPI(title="Dashboard")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

HERE = Path(__file__).parent
MASTER_URL = os.environ.get("MASTER_NODE_URL", "http://localhost:9000")
LB_URL = os.environ.get("LB_URL", "http://localhost:8000")
DASHBOARD_PORT = int(os.environ.get("DASHBOARD_PORT", "8100"))

httpx_client: httpx.AsyncClient = None

MASTER_WORKERS_ENDPOINT = f"{MASTER_URL}/workers"
MASTER_METRICS_ENDPOINT = f"{MASTER_URL}/metrics"
LB_STATS_ENDPOINT = f"{LB_URL}/stats"
LB_STRATEGY_ENDPOINT = f"{LB_URL}/strategy"
LB_WORKERS_ENDPOINT = f"{LB_URL}/workers"


async def get_client() -> httpx.AsyncClient:
    global httpx_client
    if httpx_client is None:
        httpx_client = httpx.AsyncClient(timeout=5.0)
    return httpx_client


async def fetch_json(url: str):
    try:
        client = await get_client()
        resp = await client.get(url)
        if resp.status_code == 200:
            return resp.json()
    except Exception:
        pass
    return None


@app.on_event("shutdown")
async def shutdown():
    global httpx_client
    if httpx_client:
        await httpx_client.aclose()


@app.get("/api/dashboard")
async def dashboard_api():
    workers = await fetch_json(MASTER_WORKERS_ENDPOINT)
    metrics = await fetch_json(MASTER_METRICS_ENDPOINT)
    lb_stats = await fetch_json(LB_STATS_ENDPOINT)
    strategy = await fetch_json(LB_STRATEGY_ENDPOINT)
    lb_workers = await fetch_json(LB_WORKERS_ENDPOINT)

    worker_list = []
    if workers and "workers" in workers:
        worker_list = workers["workers"]

    lb_worker_list = []
    if lb_workers and "workers" in lb_workers:
        lb_worker_list = lb_workers["workers"]

    return {
        "workers": worker_list,
        "lb_workers": lb_worker_list,
        "metrics": metrics or {},
        "stats": lb_stats or {},
        "strategy": (strategy or {}).get("strategy", "unknown"),
        "timestamp": time.time(),
    }


@app.post("/api/test-queries")
async def send_test_queries():
    client = await get_client()
    results = {"sent": 0, "failed": 0}
    for i in range(10):
        try:
            resp = await client.post(
                f"{LB_URL}/query",
                json={"query": f"Tell me something interesting about pets. query-{i}", "top_k": 3},
                timeout=30.0
            )
            if resp.status_code == 200:
                results["sent"] += 1
            else:
                results["failed"] += 1
        except Exception:
            results["failed"] += 1
    return results


@app.get("/")
async def index():
    html_path = HERE / "index.html"
    if html_path.exists():
        return FileResponse(str(html_path))
    return JSONResponse({"error": "index.html not found"}, status_code=500)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=DASHBOARD_PORT)
