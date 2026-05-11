import os
import sys
import time
import argparse
import statistics
import threading
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))
os.environ["CUDA_VISIBLE_DEVICES"] = "0"

import httpx


@dataclass
class RequestResult:
    request_id: str
    success: bool
    latency_ms: float
    status_code: Optional[int]
    worker_id: Optional[str]
    cache_hit: bool
    error: Optional[str]
    timestamp: float


@dataclass
class LoadTestConfig:
    base_url: str = "http://127.0.0.1:8000"
    total_requests: int = 100
    concurrency: int = 10
    timeout: float = 120.0
    warmup_requests: int = 5
    report_interval: int = 10


class LoadTestRunner:
    def __init__(self, config: LoadTestConfig):
        self.config = config
        self.results: List[RequestResult] = []
        self.lock = threading.Lock()
        self.stop_flag = threading.Event()
        self.start_time = 0
        self.running_requests = 0
        self.max_concurrent = 0

    def generate_payload(self, client_id: int) -> dict:
        queries = [
            "What is distributed computing?",
            "Explain neural networks in detail",
            "How does load balancing work?",
            "What is RAG in AI systems?",
            "Describe fault tolerance mechanisms",
            "Explain GPU acceleration for LLMs",
            "What are transformer models?",
            "How does caching improve performance?",
            "Describe microservice architecture",
            "What is horizontal scaling?",
            "Explain consensus algorithms",
            "How do vector databases work?",
            "What is retrieval augmented generation?",
            "Explain attention mechanisms",
            "How does Ollama GPU inference work?",
            "Describe the worker pool pattern",
            "What is round robin scheduling?",
            "Explain least connections routing",
            "How does async request handling work?",
            "What is batch processing?",
        ]
        return {
            "request_id": f"load-test-{client_id}-{int(time.time()*1000)}",
            "client_id": client_id,
            "query": queries[client_id % len(queries)],
            "top_k": 3
        }

    def send_request(self, client: httpx.Client, client_id: int) -> RequestResult:
        payload = self.generate_payload(client_id)
        start_time = time.perf_counter()
        self.running_requests += 1
        current_concurrent = self.running_requests
        if current_concurrent > self.max_concurrent:
            self.max_concurrent = current_concurrent

        try:
            response = client.post(
                f"{self.config.base_url}/query",
                json=payload,
                timeout=self.config.timeout
            )
            latency = (time.perf_counter() - start_time) * 1000

            if response.status_code == 200:
                data = response.json()
                return RequestResult(
                    request_id=payload["request_id"],
                    success=True,
                    latency_ms=latency,
                    status_code=response.status_code,
                    worker_id=data.get("worker_id"),
                    cache_hit=data.get("cache_hit", False),
                    error=None,
                    timestamp=start_time
                )
            else:
                return RequestResult(
                    request_id=payload["request_id"],
                    success=False,
                    latency_ms=latency,
                    status_code=response.status_code,
                    worker_id=None,
                    cache_hit=False,
                    error=f"HTTP {response.status_code}",
                    timestamp=start_time
                )
        except httpx.TimeoutException:
            latency = (time.perf_counter() - start_time) * 1000
            return RequestResult(
                request_id=payload["request_id"],
                success=False,
                latency_ms=latency,
                status_code=504,
                worker_id=None,
                cache_hit=False,
                error="Request timeout",
                timestamp=start_time
            )
        except Exception as e:
            latency = (time.perf_counter() - start_time) * 1000
            return RequestResult(
                request_id=payload["request_id"],
                success=False,
                latency_ms=latency,
                status_code=None,
                worker_id=None,
                cache_hit=False,
                error=str(e),
                timestamp=start_time
            )
        finally:
            self.running_requests -= 1

    def run(self) -> Dict:
        print("\n" + "=" * 70)
        print("GPU DISTRIBUTED SYSTEM - LOAD TEST")
        print("=" * 70)
        print(f"Target URL      : {self.config.base_url}/query")
        print(f"Total Requests  : {self.config.total_requests}")
        print(f"Concurrency     : {self.config.concurrency}")
        print(f"Timeout         : {self.config.timeout}s")
        print(f"Warmup          : {self.config.warmup_requests} requests")
        print("=" * 70)

        limits = httpx.Limits(
            max_connections=self.config.concurrency * 2,
            max_keepalive_connections=self.config.concurrency
        )
        client = httpx.Client(limits=limits, timeout=self.config.timeout)

        print("\n[1/4] Warming up...")
        for i in range(self.config.warmup_requests):
            self.send_request(client, i)

        print(f"[2/4] Running {self.config.total_requests} requests...")
        self.start_time = time.perf_counter()
        results = []

        with ThreadPoolExecutor(max_workers=self.config.concurrency) as executor:
            futures = [
                executor.submit(self.send_request, client, i)
                for i in range(self.config.total_requests)
            ]

            completed = 0
            for future in as_completed(futures):
                result = future.result()
                results.append(result)
                completed += 1

                if completed % self.config.report_interval == 0 or completed == self.config.total_requests:
                    elapsed = time.perf_counter() - self.start_time
                    rps = completed / elapsed if elapsed > 0 else 0
                    print(f"  Progress: {completed}/{self.config.total_requests} ({rps:.1f} req/s)")

        client.close()

        total_time = time.perf_counter() - self.start_time
        return self._generate_report(results, total_time)

    def _generate_report(self, results: List[RequestResult], total_time: float) -> Dict:
        successful = [r for r in results if r.success]
        failed = [r for r in results if not r.success]
        latencies = [r.latency_ms for r in successful]

        report = {
            "summary": self._summarize(results, successful, failed, latencies, total_time),
            "latency": self._analyze_latency(latencies),
            "workers": self._analyze_workers(successful),
            "caching": self._analyze_caching(successful),
            "errors": self._analyze_errors(failed),
        }

        self._print_report(report)
        return report

    def _summarize(self, results: List[RequestResult], successful: List[RequestResult],
                   failed: List[RequestResult], latencies: List[float], total_time: float) -> Dict:
        return {
            "total_requests": len(results),
            "successful": len(successful),
            "failed": len(failed),
            "error_rate": (len(failed) / len(results) * 100) if results else 0,
            "total_time_s": total_time,
            "throughput_rps": len(results) / total_time if total_time > 0 else 0,
            "max_concurrent": self.max_concurrent,
        }

    def _percentile(self, values: List[float], percent: float) -> float:
        if not values:
            return 0
        sorted_vals = sorted(values)
        index = int((percent / 100) * len(sorted_vals))
        index = min(index, len(sorted_vals) - 1)
        return sorted_vals[max(0, index - 1)]

    def _analyze_latency(self, latencies: List[float]) -> Dict:
        if not latencies:
            return {}

        return {
            "count": len(latencies),
            "mean_ms": statistics.mean(latencies),
            "min_ms": min(latencies),
            "max_ms": max(latencies),
            "stddev_ms": statistics.stdev(latencies) if len(latencies) > 1 else 0,
            "p50_ms": self._percentile(latencies, 50),
            "p75_ms": self._percentile(latencies, 75),
            "p90_ms": self._percentile(latencies, 90),
            "p95_ms": self._percentile(latencies, 95),
            "p99_ms": self._percentile(latencies, 99),
            "p999_ms": self._percentile(latencies, 99.9),
        }

    def _analyze_workers(self, successful: List[RequestResult]) -> Dict:
        worker_counts = {}
        for r in successful:
            wid = r.worker_id or "unknown"
            worker_counts[wid] = worker_counts.get(wid, 0) + 1

        return {
            "distribution": worker_counts,
            "worker_count": len(worker_counts),
        }

    def _analyze_caching(self, successful: List[RequestResult]) -> Dict:
        cache_hits = sum(1 for r in successful if r.cache_hit)
        cache_misses = len(successful) - cache_hits
        cache_hit_rate = (cache_hits / len(successful) * 100) if successful else 0

        return {
            "cache_hits": cache_hits,
            "cache_misses": cache_misses,
            "cache_hit_rate": cache_hit_rate,
        }

    def _analyze_errors(self, failed: List[RequestResult]) -> Dict:
        error_types = {}
        for r in failed:
            err = r.error or "Unknown"
            error_types[err] = error_types.get(err, 0) + 1

        return {
            "count": len(failed),
            "types": error_types,
        }

    def _print_report(self, report: Dict):
        s = report["summary"]
        l = report["latency"]
        w = report["workers"]
        c = report["caching"]
        e = report["errors"]

        print("\n" + "=" * 70)
        print("LOAD TEST RESULTS")
        print("=" * 70)

        print("\n[OVERALL]")
        print(f"  Total Requests     : {s['total_requests']}")
        print(f"  Successful         : {s['successful']}")
        print(f"  Failed             : {s['failed']}")
        print(f"  Error Rate         : {s['error_rate']:.2f}%")
        print(f"  Total Time         : {s['total_time_s']:.2f}s")
        print(f"  Throughput         : {s['throughput_rps']:.2f} req/s")
        print(f"  Max Concurrent     : {s['max_concurrent']}")

        if l:
            print("\n[LATENCY]")
            print(f"  Mean               : {l['mean_ms']:.2f}ms")
            print(f"  Min                : {l['min_ms']:.2f}ms")
            print(f"  Max                : {l['max_ms']:.2f}ms")
            print(f"  Std Dev            : {l['stddev_ms']:.2f}ms")
            print(f"  P50 (Median)       : {l['p50_ms']:.2f}ms")
            print(f"  P75                : {l['p75_ms']:.2f}ms")
            print(f"  P90                : {l['p90_ms']:.2f}ms")
            print(f"  P95                : {l['p95_ms']:.2f}ms")
            print(f"  P99                : {l['p99_ms']:.2f}ms")
            print(f"  P99.9              : {l['p999_ms']:.2f}ms")

        if w:
            print("\n[WORKER DISTRIBUTION]")
            for wid, count in sorted(w['distribution'].items(), key=lambda x: -x[1]):
                pct = count / s['successful'] * 100
                print(f"  {wid:15} : {count:4} requests ({pct:5.1f}%)")

        if c:
            print("\n[CACHING]")
            print(f"  Cache Hits         : {c['cache_hits']}")
            print(f"  Cache Misses       : {c['cache_misses']}")
            print(f"  Hit Rate           : {c['cache_hit_rate']:.1f}%")

        if e['count'] > 0:
            print("\n[ERRORS]")
            for err_type, count in sorted(e['types'].items(), key=lambda x: -x[1]):
                print(f"  {err_type:30} : {count} times")

        print("\n" + "=" * 70)


def run_load_test(config: LoadTestConfig):
    runner = LoadTestRunner(config)
    return runner.run()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="GPU Distributed System Load Test")

    parser.add_argument("--url", default="http://127.0.0.1:8000", help="Load balancer URL")
    parser.add_argument("--requests", type=int, default=100, help="Total requests")
    parser.add_argument("--concurrency", type=int, default=10, help="Concurrent workers")
    parser.add_argument("--timeout", type=float, default=120.0, help="Request timeout (s)")
    parser.add_argument("--warmup", type=int, default=5, help="Warmup requests")

    args = parser.parse_args()

    config = LoadTestConfig(
        base_url=args.url,
        total_requests=args.requests,
        concurrency=args.concurrency,
        timeout=args.timeout,
        warmup_requests=args.warmup
    )

    run_load_test(config)