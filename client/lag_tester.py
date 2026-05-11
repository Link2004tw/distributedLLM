import os
import sys
import time
import argparse
import statistics
import threading
from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple
from collections import defaultdict
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))
os.environ["CUDA_VISIBLE_DEVICES"] = "0"

import httpx


@dataclass
class LatencyResult:
    request_id: str
    sent_time: float
    received_time: float
    latency_ms: float
    status_code: int
    worker_id: str
    cache_hit: bool
    error: Optional[str]


@dataclass
class LagMetrics:
    timestamp: float
    active_requests: int
    avg_latency_ms: float
    p95_latency_ms: float
    queue_depth_estimate: int


class LatencyLagTester:
    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8000",
        duration_seconds: int = 30,
        request_interval_ms: int = 100,
        timeout: float = 120.0
    ):
        self.base_url = base_url
        self.duration_seconds = duration_seconds
        self.request_interval_ms = request_interval_ms
        self.timeout = timeout

        self.results: List[LatencyResult] = []
        self.lag_samples: List[LagMetrics] = []
        self.lock = threading.Lock()
        self.stop_flag = threading.Event()
        self.worker_thread: Optional[threading.Thread] = None

    def send_request_sync(self, client: httpx.Client, request_id: str) -> LatencyResult:
        payload = {
            "request_id": request_id,
            "query": "What is machine learning and how does it work?",
            "top_k": 3
        }

        sent_time = time.perf_counter()
        try:
            response = client.post(
                f"{self.base_url}/query",
                json=payload,
                timeout=self.timeout
            )
            received_time = time.perf_counter()
            latency_ms = (received_time - sent_time) * 1000

            if response.status_code == 200:
                data = response.json()
                return LatencyResult(
                    request_id=request_id,
                    sent_time=sent_time,
                    received_time=received_time,
                    latency_ms=latency_ms,
                    status_code=response.status_code,
                    worker_id=data.get("worker_id", "unknown"),
                    cache_hit=data.get("cache_hit", False),
                    error=None
                )
            else:
                return LatencyResult(
                    request_id=request_id,
                    sent_time=sent_time,
                    received_time=received_time,
                    latency_ms=latency_ms,
                    status_code=response.status_code,
                    worker_id="",
                    cache_hit=False,
                    error=f"HTTP {response.status_code}"
                )
        except Exception as e:
            received_time = time.perf_counter()
            return LatencyResult(
                request_id=request_id,
                sent_time=sent_time,
                received_time=received_time,
                latency_ms=(received_time - sent_time) * 1000,
                status_code=0,
                worker_id="",
                cache_hit=False,
                error=str(e)
            )

    def send_continuous_requests(self):
        client = httpx.Client(timeout=self.timeout)
        request_count = 0
        start_time = time.perf_counter()

        while not self.stop_flag.is_set():
            elapsed = time.perf_counter() - start_time
            if elapsed >= self.duration_seconds:
                break

            request_id = f"lag-test-{request_count}-{int(elapsed*1000)}"
            result = self.send_request_sync(client, request_id)

            with self.lock:
                self.results.append(result)

            next_send = start_time + (request_count + 1) * (self.request_interval_ms / 1000)
            sleep_time = next_send - time.perf_counter()
            if sleep_time > 0:
                time.sleep(sleep_time)

            request_count += 1

        client.close()

    def collect_lag_samples(self):
        start_time = time.perf_counter()
        while not self.stop_flag.is_set():
            elapsed = time.perf_counter() - start_time
            if elapsed >= self.duration_seconds:
                break

            with self.lock:
                recent = [r for r in self.results if (time.perf_counter() - r.received_time) < 5]
                if recent:
                    latencies = [r.latency_ms for r in recent]
                    sorted_lat = sorted(latencies)
                    p95_idx = int(len(sorted_lat) * 0.95)
                    p95 = sorted_lat[p95_idx] if p95_idx < len(sorted_lat) else sorted_lat[-1]

                    active_count = len([r for r in self.results if r.received_time > time.perf_counter() - 1])

                    sample = LagMetrics(
                        timestamp=time.perf_counter() - start_time,
                        active_requests=active_count,
                        avg_latency_ms=statistics.mean(latencies),
                        p95_latency_ms=p95,
                        queue_depth_estimate=int(statistics.mean(latencies) / 100)
                    )
                    self.lag_samples.append(sample)

            time.sleep(0.5)

    def run(self) -> Dict:
        print("\n" + "=" * 70)
        print("LATENCY & LAG TEST")
        print("=" * 70)
        print(f"Target URL           : {self.base_url}/query")
        print(f"Duration             : {self.duration_seconds}s")
        print(f"Request Interval     : {self.request_interval_ms}ms")
        print(f"Expected Rate        : {1000/self.request_interval_ms:.1f} req/s")
        print("=" * 70)

        self.results = []
        self.lag_samples = []
        self.stop_flag.clear()

        sender = threading.Thread(target=self.send_continuous_requests)
        sampler = threading.Thread(target=self.collect_lag_samples)

        print("\n[Starting test...]")
        start_time = time.perf_counter()
        sender.start()
        sampler.start()

        sender.join()
        self.stop_flag.set()
        sampler.join()
        total_time = time.perf_counter() - start_time

        return self._generate_lag_report(total_time)

    def _percentile(self, values: List[float], percent: float) -> float:
        if not values:
            return 0
        sorted_vals = sorted(values)
        index = int((percent / 100) * len(sorted_vals))
        index = min(index, len(sorted_vals) - 1)
        return sorted_vals[max(0, index - 1)]

    def _detect_lag_spikes(self, latencies: List[float], window_size: int = 10) -> List[Dict]:
        if len(latencies) < window_size:
            return []

        spikes = []
        sorted_lat = sorted(latencies)
        p95 = self._percentile(latencies, 95)
        p99 = self._percentile(latencies, 99)

        for i in range(len(latencies) - window_size + 1):
            window = latencies[i:i + window_size]
            window_mean = statistics.mean(window)
            if window_mean > p95 * 2:
                spikes.append({
                    "index": i,
                    "start": i,
                    "end": i + window_size,
                    "avg_latency_ms": window_mean,
                    "peak_latency_ms": max(window),
                })

        return spikes

    def _generate_lag_report(self, total_time: float) -> Dict:
        successful = [r for r in self.results if r.error is None]
        failed = [r for r in self.results if r.error is not None]
        latencies = [r.latency_ms for r in successful]

        report = {
            "summary": {
                "total_requests": len(self.results),
                "successful": len(successful),
                "failed": len(failed),
                "test_duration_s": total_time,
                "actual_throughput_rps": len(self.results) / total_time if total_time > 0 else 0,
            },
            "latency_stats": self._compute_latency_stats(latencies),
            "lag_analysis": self._analyze_lag(),
            "worker_stats": self._compute_worker_stats(successful),
            "spike_detection": self._detect_lag_spikes(latencies),
            "time_series": self._generate_time_series(),
        }

        self._print_lag_report(report)
        return report

    def _compute_latency_stats(self, latencies: List[float]) -> Dict:
        if not latencies:
            return {}

        return {
            "count": len(latencies),
            "mean_ms": statistics.mean(latencies),
            "median_ms": self._percentile(latencies, 50),
            "stddev_ms": statistics.stdev(latencies) if len(latencies) > 1 else 0,
            "min_ms": min(latencies),
            "max_ms": max(latencies),
            "p50_ms": self._percentile(latencies, 50),
            "p75_ms": self._percentile(latencies, 75),
            "p90_ms": self._percentile(latencies, 90),
            "p95_ms": self._percentile(latencies, 95),
            "p99_ms": self._percentile(latencies, 99),
            "p999_ms": self._percentile(latencies, 99.9),
        }

    def _analyze_lag(self) -> Dict:
        if not self.lag_samples:
            return {}

        avg_latencies = [s.avg_latency_ms for s in self.lag_samples]
        p95_latencies = [s.p95_latency_ms for s in self.lag_samples]

        lag_threshold_ms = statistics.mean(avg_latencies) * 2
        high_lag_samples = [s for s in self.lag_samples if s.avg_latency_ms > lag_threshold_ms]

        return {
            "avg_latency_samples": len(self.lag_samples),
            "baseline_avg_ms": statistics.mean(avg_latencies) if avg_latencies else 0,
            "lag_threshold_ms": lag_threshold_ms,
            "high_lag_events": len(high_lag_samples),
            "max_p95_ms": max(p95_latencies) if p95_latencies else 0,
            "lag_score": len(high_lag_samples) / len(self.lag_samples) if self.lag_samples else 0,
        }

    def _compute_worker_stats(self, successful: List[LatencyResult]) -> Dict:
        worker_latencies = defaultdict(list)
        for r in successful:
            worker_latencies[r.worker_id].append(r.latency_ms)

        worker_stats = {}
        for wid, latencies in worker_latencies.items():
            worker_stats[wid] = {
                "count": len(latencies),
                "avg_ms": statistics.mean(latencies),
                "p95_ms": self._percentile(latencies, 95),
                "min_ms": min(latencies),
                "max_ms": max(latencies),
            }

        return {
            "worker_count": len(worker_stats),
            "workers": worker_stats,
        }

    def _generate_time_series(self) -> List[Dict]:
        return [
            {
                "timestamp_s": s.timestamp,
                "avg_ms": s.avg_latency_ms,
                "p95_ms": s.p95_latency_ms,
                "active": s.active_requests,
            }
            for s in self.lag_samples
        ]

    def _print_lag_report(self, report: Dict):
        s = report["summary"]
        l = report["latency_stats"]
        lag = report["lag_analysis"]
        w = report["worker_stats"]
        spikes = report["spike_detection"]

        print("\n" + "=" * 70)
        print("LAG TEST RESULTS")
        print("=" * 70)

        print("\n[SUMMARY]")
        print(f"  Total Requests     : {s['total_requests']}")
        print(f"  Successful         : {s['successful']}")
        print(f"  Failed             : {s['failed']}")
        print(f"  Duration           : {s['test_duration_s']:.2f}s")
        print(f"  Actual Throughput   : {s['actual_throughput_rps']:.2f} req/s")

        if l:
            print("\n[LATENCY STATISTICS]")
            print(f"  Mean Latency       : {l['mean_ms']:.2f}ms")
            print(f"  Median Latency     : {l['median_ms']:.2f}ms")
            print(f"  Std Deviation      : {l['stddev_ms']:.2f}ms")
            print(f"  Min Latency        : {l['min_ms']:.2f}ms")
            print(f"  Max Latency        : {l['max_ms']:.2f}ms")
            print(f"  P50                : {l['p50_ms']:.2f}ms")
            print(f"  P90                : {l['p90_ms']:.2f}ms")
            print(f"  P95                : {l['p95_ms']:.2f}ms")
            print(f"  P99                : {l['p99_ms']:.2f}ms")
            print(f"  P99.9              : {l['p999_ms']:.2f}ms")

        if lag:
            print("\n[LAG ANALYSIS]")
            print(f"  Lag Threshold      : {lag['lag_threshold_ms']:.2f}ms (2x mean)")
            print(f"  High Lag Events    : {lag['high_lag_events']}")
            print(f"  Max P95 Latency    : {lag['max_p95_ms']:.2f}ms")
            print(f"  Lag Score          : {lag['lag_score']*100:.1f}%")
            if lag['lag_score'] > 0.1:
                print("  [!] WARNING: Significant lag detected!")
            elif lag['lag_score'] > 0:
                print("  [OK] Lag within acceptable range")
            else:
                print("  [OK] No significant lag detected")

        if w and w.get("workers"):
            print("\n[WORKER STATISTICS]")
            for wid, stats in sorted(w["workers"].items()):
                print(f"  [{wid}] Count: {stats['count']:4} | Avg: {stats['avg_ms']:7.1f}ms | P95: {stats['p95_ms']:7.1f}ms")

        if spikes:
            print("\n[LAG SPIKES DETECTED]")
            for spike in spikes[:5]:
                print(f"  At request {spike['index']}: avg={spike['avg_latency_ms']:.0f}ms, peak={spike['peak_latency_ms']:.0f}ms")
        else:
            print("\n[LAG SPIKES] No significant spikes detected")

        print("\n" + "=" * 70)


def run_lag_test(
    base_url: str = "http://127.0.0.1:8000",
    duration: int = 30,
    interval_ms: int = 100,
    timeout: float = 120.0
):
    tester = LatencyLagTester(
        base_url=base_url,
        duration_seconds=duration,
        request_interval_ms=interval_ms,
        timeout=timeout
    )
    return tester.run()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Latency & Lag Test")

    parser.add_argument("--url", default="http://127.0.0.1:8000", help="Load balancer URL")
    parser.add_argument("--duration", type=int, default=30, help="Test duration (s)")
    parser.add_argument("--interval", type=int, default=100, help="Request interval (ms)")
    parser.add_argument("--timeout", type=float, default=120.0, help="Request timeout (s)")

    args = parser.parse_args()

    run_lag_test(
        base_url=args.url,
        duration=args.duration,
        interval_ms=args.interval,
        timeout=args.timeout
    )