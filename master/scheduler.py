import os
from typing import Dict, List, Optional
import httpx

from common.models import RoutingStrategy, WorkerInfo


LB_STRATEGY = os.environ.get("LB_STRATEGY", "round_robin")


class Scheduler:

    def __init__(self, load_balancer=None):
        self.lb = load_balancer
        self._failed_workers: set = set()

    def distribute_task(self, task_data: dict, strategy: str = LB_STRATEGY) -> Optional[dict]:
        from lb.load_balancer import LoadBalancer
        lb = self.lb or LoadBalancer()
        worker = lb.get_next_server(strategy)
        if not worker:
            return None
        try:
            resp = httpx.post(
                f"http://localhost:{worker['port']}/query",
                json=task_data,
                timeout=60.0,
            )
            if resp.status_code == 200:
                return resp.json()
        except Exception:
            pass
        return None

    def monitor_workers(self) -> Dict[str, dict]:
        workers = {}
        for port in range(8001, 8005):
            wid = f"worker-{port - 8000}"
            try:
                resp = httpx.get(f"http://localhost:{port}/health", timeout=3.0)
                if resp.status_code == 200:
                    data = resp.json()
                    workers[wid] = {
                        "healthy": data.get("healthy", True),
                        "active_connections": data.get("active_connections", 0),
                        "avg_latency_ms": data.get("avg_latency_ms", 0),
                    }
                else:
                    workers[wid] = {"healthy": False}
            except Exception:
                workers[wid] = {"healthy": False}
        return workers

    def handle_failure(self, worker_id: str) -> dict:
        self._failed_workers.add(worker_id)
        try:
            httpx.post(
                f"http://localhost:8005/worker/{worker_id}/disable",
                timeout=5.0,
            )
        except Exception:
            pass
        try:
            httpx.delete(
                f"http://localhost:9000/worker/{worker_id}",
                timeout=5.0,
            )
        except Exception:
            pass
        return {"status": "handled", "worker_id": worker_id}
