from typing import Dict, List, Optional

from common.models import RoutingStrategy, WorkerInfo


class WorkerScheduler:

    def __init__(self, workers: Dict[str, WorkerInfo], latency_weight: float = 0.01):
        self.workers = workers
        self.round_robin_index = 0
        self.latency_weight = latency_weight

    def update_workers(self, workers: Dict[str, WorkerInfo]) -> None:
        self.workers = workers

    def healthy_workers(self) -> List[WorkerInfo]:
        return [worker for worker in self.workers.values() if worker.healthy]

    def score_worker(self, worker: WorkerInfo) -> float:
        return worker.active_connections + worker.avg_latency_ms * self.latency_weight

    def select_worker(self, strategy: RoutingStrategy) -> Optional[WorkerInfo]:
        healthy = self.healthy_workers()
        if not healthy:
            return None

        if strategy == RoutingStrategy.ROUND_ROBIN:
            worker = healthy[self.round_robin_index % len(healthy)]
            self.round_robin_index = (self.round_robin_index + 1) % len(healthy)
            return worker

        if strategy == RoutingStrategy.LEAST_CONNECTIONS:
            return min(healthy, key=lambda w: w.active_connections)

        if strategy == RoutingStrategy.LOAD_AWARE:
            return min(healthy, key=self.score_worker)

        return healthy[0]
