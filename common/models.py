from dataclasses import dataclass, field
from typing import Optional, List
from enum import Enum


class RoutingStrategy(str, Enum):
    ROUND_ROBIN = "round_robin"
    LEAST_CONNECTIONS = "least_connections"
    LOAD_AWARE = "load_aware"


@dataclass
class QueryRequest:
    query: str
    user_id: str
    strategy: RoutingStrategy = RoutingStrategy.LEAST_CONNECTIONS
    top_k: int = 3


@dataclass
class QueryResponse:
    answer: str
    sources: List[str] = field(default_factory=list)
    latency_ms: float = 0.0
    worker_id: str = ""


@dataclass
class WorkerInfo:
    worker_id: str
    port: int
    host: str = "localhost"
    healthy: bool = True
    active_connections: int = 0
    avg_latency_ms: float = 0.0
    last_heartbeat: float = 0.0


@dataclass
class WorkerRegistration:
    worker_id: str
    port: int
    host: str = "localhost"


@dataclass
class HealthCheck:
    worker_id: str
    healthy: bool
    active_connections: int = 0
    avg_latency_ms: float = 0.0


@dataclass
class MetricsSummary:
    total_requests: int = 0
    avg_latency_ms: float = 0.0
    failed_workers: int = 0
    worker_stats: dict = field(default_factory=dict)


@dataclass
class RequeueRequest:
    original_request: QueryRequest
    worker_id: str