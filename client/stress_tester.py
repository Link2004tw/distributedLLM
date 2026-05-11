import os
import sys
import time
import argparse
import statistics
import threading
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed

sys.path.insert(0, os.path.dirname(__file__))
os.environ["CUDA_VISIBLE_DEVICES"] = "0"

import httpx


@dataclass
class StressResult:
    phase: int
    concurrency: int
    requests: int
    successful: int
    failed: int
    avg_latency_ms: float
    p95_latency_ms: float
    throughput_rps: float
    error_rate: float


@dataclass
class BenchmarkConfig:
    base_url: str
    phases: List[Tuple[int, int]]
    timeout: float = 120.0
    warmup: int = 5


class StressTester:
    def __init__(self, base_url: str, timeout: float = 120.0):
        self.base_url = base_url
        self.timeout = timeout
        self.results: List[StressResult] = []
        self.lock = threading.Lock()

    def run_phase(self, phase_num: int, concurrency: int, total_requests: int) -> StressResult:
        print(f"\n  Phase {phase_num}: {concurrency} concurrent workers, {total_requests} requests...")

        client = httpx.Client(timeout=self.timeout)

        for i in range(5):
            client.post(f"{self.base_url}/query", json={"query": "warmup", "top_k": 1})

        latencies = []
        successful = 0
        failed = 0
        start_time = time.perf_counter()

        with ThreadPoolExecutor(max_workers=concurrency) as executor:
            futures = []
            for i in range(total_requests):
                future = executor.submit(self._send_request, client, f"stress-{phase_num}-{i}")
                futures.append(future)

            for future in as_completed(futures):
                result = future.result()
                if result["success"]:
                    successful += 1
                    latencies.append(result["latency"])
                else:
                    failed += 1

        elapsed = time.perf_counter() - start_time
        throughput = total_requests / elapsed if elapsed > 0 else 0

        p95 = self._percentile(latencies, 95) if latencies else 0

        result = StressResult(
            phase=phase_num,
            concurrency=concurrency,
            requests=total_requests,
            successful=successful,
            failed=failed,
            avg_latency_ms=statistics.mean(latencies) if latencies else 0,
            p95_latency_ms=p95,
            throughput_rps=throughput,
            error_rate=(failed / total_requests * 100) if total_requests > 0 else 0
        )

        client.close()
        return result

    def _send_request(self, client: httpx.Client, request_id: str) -> Dict:
        start = time.perf_counter()
        try:
            response = client.post(
                f"{self.base_url}/query",
                json={"request_id": request_id, "query": "What is AI?", "top_k": 1},
                timeout=self.timeout
            )
            latency = (time.perf_counter() - start) * 1000
            return {"success": response.status_code == 200, "latency": latency}
        except Exception:
            return {"success": False, "latency": (time.perf_counter() - start) * 1000}

    def _percentile(self, values: List[float], percent: float) -> float:
        if not values:
            return 0
        sorted_vals = sorted(values)
        index = int((percent / 100) * len(sorted_vals))
        return sorted_vals[min(index, len(sorted_vals) - 1)]

    def run_stress_test(self, phases: List[Tuple[int, int]]) -> List[StressResult]:
        print("\n" + "=" * 70)
        print("STRESS TEST - Progressive Load")
        print("=" * 70)
        print(f"Target URL  : {self.base_url}/query")
        print(f"Phases      : {phases}")
        print("=" * 70)

        results = []
        for i, (concurrency, requests) in enumerate(phases, 1):
            result = self.run_phase(i, concurrency, requests)
            results.append(result)

            print(f"  [OK] Success: {result.successful}, Throughput: {result.throughput_rps:.2f} req/s, P95: {result.p95_latency_ms:.0f}ms")

            if result.error_rate > 20:
                print(f"  [!] High error rate ({result.error_rate:.1f}%) - system under stress")
                if result.error_rate > 50:
                    print("  [!] Stopping stress test - system overloaded")
                    break

        return results

    def _print_stress_report(self, results: List[StressResult]):
        print("\n" + "=" * 70)
        print("STRESS TEST RESULTS")
        print("=" * 70)
        print(f"\n{'Phase':<6} {'Concurrency':<12} {'Requests':<10} {'Success':<10} {'Failed':<8} {'Avg(ms)':<10} {'P95(ms)':<10} {'RPS':<10} {'Error%':<8}")
        print("-" * 90)

        for r in results:
            print(f"{r.phase:<6} {r.concurrency:<12} {r.requests:<10} {r.successful:<10} {r.failed:<8} {r.avg_latency_ms:<10.1f} {r.p95_latency_ms:<10.1f} {r.throughput_rps:<10.2f} {r.error_rate:<8.1f}")

        if len(results) > 1:
            print("\n[SCALING ANALYSIS]")
            first = results[0]
            last = results[-1]
            print(f"  Concurrency increase    : {first.concurrency} -> {last.concurrency} ({last.concurrency/first.concurrency:.1f}x)")
            print(f"  Throughput change       : {first.throughput_rps:.2f} -> {last.throughput_rps:.2f} req/s")
            print(f"  Latency change          : {first.avg_latency_ms:.0f}ms -> {last.avg_latency_ms:.0f}ms")

            if last.throughput_rps > first.throughput_rps:
                print("  [OK] System scales with load")
            else:
                print("  [!] System may be bottlenecking")

        print("\n" + "=" * 70)


class BenchmarkComparison:
    def __init__(self, base_url: str = "http://127.0.0.1:8000", timeout: float = 120.0):
        self.base_url = base_url
        self.timeout = timeout

    def check_services(self) -> Dict:
        print("\n" + "=" * 70)
        print("SERVICE HEALTH CHECK")
        print("=" * 70)

        results = {}
        client = httpx.Client(timeout=10.0)

        try:
            r = client.get(f"{self.base_url}/health")
            results["load_balancer"] = {"status": "healthy" if r.status_code == 200 else "unhealthy"}
        except Exception as e:
            results["load_balancer"] = {"status": "unreachable", "error": str(e)}

        try:
            r = client.get(f"{self.base_url}/stats")
            if r.status_code == 200:
                data = r.json()
                results["stats"] = data
        except Exception:
            pass

        try:
            r = client.get(f"{self.base_url}/workers")
            if r.status_code == 200:
                data = r.json()
                workers = data.get("workers", [])
                results["workers"] = {
                    "count": len(workers),
                    "healthy": sum(1 for w in workers if w.get("healthy")),
                    "workers": workers
                }
        except Exception:
            pass

        client.close()
        return results

    def benchmark_single_endpoint(self, endpoint: str, payload: dict, runs: int = 10) -> Dict:
        client = httpx.Client(timeout=self.timeout)

        latencies = []
        for _ in range(runs):
            start = time.perf_counter()
            try:
                r = client.post(f"{self.base_url}{endpoint}", json=payload)
                latency = (time.perf_counter() - start) * 1000
                latencies.append({"success": r.status_code == 200, "latency": latency})
            except Exception as e:
                latencies.append({"success": False, "latency": 0, "error": str(e)})

        client.close()

        successful = [l["latency"] for l in latencies if l["success"]]
        return {
            "runs": runs,
            "successful": len(successful),
            "failed": runs - len(successful),
            "avg_ms": statistics.mean(successful) if successful else 0,
            "min_ms": min(successful) if successful else 0,
            "max_ms": max(successful) if successful else 0,
            "p95_ms": self._percentile(successful, 95) if successful else 0,
        }

    def benchmark_single_endpoint_get(self, endpoint: str, runs: int = 10) -> Dict:
        client = httpx.Client(timeout=self.timeout)

        latencies = []
        for _ in range(runs):
            start = time.perf_counter()
            try:
                r = client.get(f"{self.base_url}{endpoint}")
                latency = (time.perf_counter() - start) * 1000
                latencies.append({"success": r.status_code == 200, "latency": latency})
            except Exception as e:
                latencies.append({"success": False, "latency": 0, "error": str(e)})

        client.close()

        successful = [l["latency"] for l in latencies if l["success"]]
        return {
            "runs": runs,
            "successful": len(successful),
            "failed": runs - len(successful),
            "avg_ms": statistics.mean(successful) if successful else 0,
            "min_ms": min(successful) if successful else 0,
            "max_ms": max(successful) if successful else 0,
            "p95_ms": self._percentile(successful, 95) if successful else 0,
        }

    def _percentile(self, values: List[float], percent: float) -> float:
        if not values:
            return 0
        sorted_vals = sorted(values)
        index = int((percent / 100) * len(sorted_vals))
        return sorted_vals[min(index, len(sorted_vals) - 1)]

    def run_benchmark(self) -> Dict:
        print("\n" + "=" * 70)
        print("SYSTEM BENCHMARK")
        print("=" * 70)

        health = self.check_services()

        print(f"\nLoad Balancer: {health.get('load_balancer', {}).get('status', 'unknown')}")
        if "workers" in health:
            print(f"Workers: {health['workers']['healthy']}/{health['workers']['count']} healthy")

        benchmarks = {}

        print("\n[Benchmarking /query endpoint...]")
        benchmarks["query"] = self.benchmark_single_endpoint(
            "/query",
            {"query": "What is machine learning?", "top_k": 1},
            runs=10
        )

        print("\n[Benchmarking /health endpoint...]")
        benchmarks["health"] = self.benchmark_single_endpoint_get(
            "/health",
            runs=20
        )

        print("\n[Benchmarking /workers endpoint...]")
        benchmarks["workers"] = self.benchmark_single_endpoint_get(
            "/workers",
            runs=20
        )

        self._print_benchmark_results(benchmarks, health)
        return {"health": health, "benchmarks": benchmarks}

    def _print_benchmark_results(self, benchmarks: Dict, health: Dict):
        print("\n" + "=" * 70)
        print("BENCHMARK RESULTS")
        print("=" * 70)

        print("\n[QUERY ENDPOINT (/query)]")
        q = benchmarks.get("query", {})
        print(f"  Runs       : {q.get('runs', 0)}")
        print(f"  Success    : {q.get('successful', 0)}")
        print(f"  Avg        : {q.get('avg_ms', 0):.1f}ms")
        print(f"  Min        : {q.get('min_ms', 0):.1f}ms")
        print(f"  Max        : {q.get('max_ms', 0):.1f}ms")
        print(f"  P95        : {q.get('p95_ms', 0):.1f}ms")

        print("\n[HEALTH ENDPOINT (/health)]")
        h = benchmarks.get("health", {})
        print(f"  Runs       : {h.get('runs', 0)}")
        print(f"  Success    : {h.get('successful', 0)}")
        print(f"  Avg        : {h.get('avg_ms', 0):.1f}ms")
        print(f"  P95        : {h.get('p95_ms', 0):.1f}ms")

        print("\n[WORKERS ENDPOINT (/workers)]")
        w = benchmarks.get("workers", {})
        print(f"  Runs       : {w.get('runs', 0)}")
        print(f"  Success    : {w.get('successful', 0)}")
        print(f"  Avg        : {w.get('avg_ms', 0):.1f}ms")
        print(f"  P95        : {w.get('p95_ms', 0):.1f}ms")

        if "workers" in health:
            print("\n[WORKER DETAILS]")
            for worker in health["workers"].get("workers", []):
                status = "[OK]" if worker.get("healthy") else "[FAIL]"
                print(f"  {status} {worker.get('worker_id', 'unknown'):15} | GPU: {worker.get('gpu_utilization', 0)}% | Mem: {worker.get('gpu_memory_mb', 0)}MB")

        print("\n" + "=" * 70)


def run_stress_test(url: str, phases: List[Tuple[int, int]]):
    tester = StressTester(base_url=url)
    results = tester.run_stress_test(phases)
    tester._print_stress_report(results)
    return results


def run_benchmark(url: str):
    bench = BenchmarkComparison(base_url=url)
    bench.run_benchmark()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Stress Test & Benchmark")

    parser.add_argument("--url", default="http://127.0.0.1:8000", help="Load balancer URL")
    parser.add_argument("--mode", choices=["stress", "benchmark", "both"], default="benchmark", help="Test mode")
    parser.add_argument("--duration", type=int, default=30, help="Test duration (s)")

    args = parser.parse_args()

    if args.mode in ["stress", "both"]:
        phases = [
            (5, 20),
            (10, 50),
            (20, 100),
        ]
        run_stress_test(args.url, phases)

    if args.mode in ["benchmark", "both"]:
        run_benchmark(args.url)