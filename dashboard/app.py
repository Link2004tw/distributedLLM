import os
import time
from pathlib import Path

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates


MASTER_URL = os.getenv("MASTER_URL", "http://127.0.0.1:9000")

BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"

app = FastAPI(title="Distributed LLM Admin Dashboard")

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def fallback_metrics():
    return {
        "total_requests": 0,
        "successful_requests": 0,
        "failed_requests": 0,
        "average_latency_ms": 0,
        "avg_latency_ms": 0,
        "failed_workers": 0,
        "p50_latency_ms": 0,
        "p95_latency_ms": 0,
        "p99_latency_ms": 0,
        "throughput_rps": 0,
        "active_connections": 0,
        "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "_warning": "Master metrics endpoint is not available yet."
    }


def fallback_workers():
    return {
        "workers": [
            {
                "worker_id": "worker-1",
                "host": "127.0.0.1",
                "port": 8001,
                "healthy": False,
                "active_connections": 0,
                "avg_latency_ms": 0,
                "last_heartbeat": None
            },
            {
                "worker_id": "worker-2",
                "host": "127.0.0.1",
                "port": 8002,
                "healthy": False,
                "active_connections": 0,
                "avg_latency_ms": 0,
                "last_heartbeat": None
            },
            {
                "worker_id": "worker-3",
                "host": "127.0.0.1",
                "port": 8003,
                "healthy": False,
                "active_connections": 0,
                "avg_latency_ms": 0,
                "last_heartbeat": None
            },
            {
                "worker_id": "worker-4",
                "host": "127.0.0.1",
                "port": 8004,
                "healthy": False,
                "active_connections": 0,
                "avg_latency_ms": 0,
                "last_heartbeat": None
            }
        ],
        "_warning": "Master workers endpoint is not available yet."
    }


async def fetch_from_master(path: str, fallback_function):
    url = f"{MASTER_URL}{path}"
    try:
        async with httpx.AsyncClient(timeout=2.0) as client:
            response = await client.get(url)
            response.raise_for_status()
            return response.json()
    except Exception as e:
        data = fallback_function()
        data["_error"] = str(e)
        return data


@app.get("/", response_class=HTMLResponse)
async def dashboard_home(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={
            "request": request,
            "master_url": MASTER_URL
        }
    )


@app.get("/api/metrics")
async def get_metrics():
    return await fetch_from_master("/metrics", fallback_metrics)


@app.get("/api/workers")
async def get_workers():
    return await fetch_from_master("/workers", fallback_workers)


@app.get("/api/overview")
async def get_overview():
    metrics = await fetch_from_master("/metrics", fallback_metrics)
    workers_data = await fetch_from_master("/workers", fallback_workers)
    return {"metrics": metrics, "workers": workers_data.get("workers", [])}


@app.get("/api/data")
async def get_data():
    metrics_raw = await fetch_from_master("/metrics", fallback_metrics)
    workers_raw = await fetch_from_master("/workers", fallback_workers)
    workers_list = workers_raw.get("workers", [])

    master_online = "_error" not in metrics_raw and "_error" not in workers_raw

    metrics = dict(metrics_raw)
    metrics.setdefault("avg_latency_ms", metrics.get("average_latency_ms", 0))
    metrics.setdefault("failed_workers", 0)

    workers = []
    for w in workers_list:
        workers.append({
            "worker_id": w.get("worker_id") or w.get("id", "unknown"),
            "healthy": w.get("healthy", w.get("status") == "healthy"),
            "host": w.get("host", "127.0.0.1"),
            "port": w.get("port", 0),
            "active_connections": w.get("active_connections", 0),
            "avg_latency_ms": w.get("avg_latency_ms") or w.get("latency_ms", 0),
            "last_heartbeat": w.get("last_heartbeat", None)
        })

    return {
        "master_online": master_online,
        "metrics": metrics,
        "workers": workers,
        "timestamp": time.time()
    }


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "service": "dashboard",
        "master_url": MASTER_URL
    }