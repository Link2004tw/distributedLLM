from dataclasses import dataclass
from enum import Enum
from typing import Dict


@dataclass
class Request:
    id: int
    query: str


@dataclass
class Response:
    id: int
    result: str
    latency: float


class RoutingStrategy(str, Enum):
    ROUND_ROBIN = "round_robin"
    LEAST_CONNECTIONS = "least_connections"
    LOAD_AWARE = "load_aware"


@dataclass
class WorkerInfo:
    worker_id: str
    port: int
    host: str
    healthy: bool = True
    active_connections: int = 0
    avg_latency_ms: float = 0.0
    last_heartbeat: float = 0.0


@dataclass
class HealthCheck:
    worker_id: str
    healthy: bool
    active_connections: int
    avg_latency_ms: float


@dataclass
class MetricsSummary:
    total_requests: int
    avg_latency_ms: float
    failed_workers: int
    worker_stats: Dict[str, int]
