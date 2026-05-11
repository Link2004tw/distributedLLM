import os
import sys
import time
import json
import argparse
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from client.load_generator import LoadTestConfig, run_load_test


def run_stress_test(
    base_url: str = "http://127.0.0.1:8000",
    levels: list = None,
    requests_per_level: int = 100,
    timeout: float = 120.0
):
    if levels is None:
        levels = [10, 50, 100, 250, 500, 1000]

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    results = []

    print("\n" + "=" * 70)
    print("1000+ CONCURRENT USERS STRESS TEST")
    print("=" * 70)
    print(f"Base URL         : {base_url}")
    print(f"Test Levels      : {levels}")
    print(f"Requests/Level   : {requests_per_level}")
    print("=" * 70)

    for concurrency in levels:
        print(f"\n{'='*70}")
        print(f"TESTING: {concurrency} Concurrent Users")
        print(f"{'='*70}")

        config = LoadTestConfig(
            base_url=base_url,
            total_requests=requests_per_level,
            concurrency=concurrency,
            timeout=timeout,
            warmup_requests=3
        )

        result = run_load_test(config)

        summary = result["summary"]
        latency = result["latency"]

        test_result = {
            "timestamp": datetime.now().isoformat(),
            "concurrency": concurrency,
            "requests": requests_per_level,
            "total_requests": summary["total_requests"],
            "successful": summary["successful"],
            "failed": summary["failed"],
            "error_rate": summary["error_rate"],
            "total_time_s": summary["total_time_s"],
            "throughput_rps": summary["throughput_rps"],
            "max_concurrent": summary["max_concurrent"],
            "latency": {
                "mean_ms": latency.get("mean_ms", 0),
                "min_ms": latency.get("min_ms", 0),
                "max_ms": latency.get("max_ms", 0),
                "p50_ms": latency.get("p50_ms", 0),
                "p75_ms": latency.get("p75_ms", 0),
                "p90_ms": latency.get("p90_ms", 0),
                "p95_ms": latency.get("p95_ms", 0),
                "p99_ms": latency.get("p99_ms", 0),
            }
        }
        results.append(test_result)

        print(f"\n  Results:")
        print(f"    Throughput : {summary['throughput_rps']:.2f} req/s")
        print(f"    Error Rate : {summary['error_rate']:.2f}%")
        print(f"    P95 Latency: {latency.get('p95_ms', 0):.2f}ms")

        time.sleep(2)

    print("\n" + "=" * 70)
    print("STRESS TEST SUMMARY")
    print("=" * 70)
    print(f"{'Concurrency':>12} {'Throughput':>12} {'Error%':>8} {'P95(ms)':>10} {'P99(ms)':>10}")
    print("-" * 55)
    for r in results:
        print(f"{r['concurrency']:>12} {r['throughput_rps']:>11.2f} {r['error_rate']:>7.2f}% {r['latency']['p95_ms']:>9.2f} {r['latency']['p99_ms']:>9.2f}")
    print("=" * 70)

    output_file = Path(__file__).parent / f"stress_test_results_{timestamp}.json"
    with open(output_file, "w") as f:
        json.dump({
            "test_timestamp": timestamp,
            "base_url": base_url,
            "levels": levels,
            "requests_per_level": requests_per_level,
            "results": results
        }, f, indent=2)

    print(f"\nResults saved to: {output_file}")

    return results


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="1000+ Concurrent Users Stress Test")
    parser.add_argument("--url", default="http://127.0.0.1:8000", help="Load balancer URL")
    parser.add_argument("--levels", type=str, default="10,50,100,250,500,1000",
                        help="Comma-separated concurrency levels")
    parser.add_argument("--requests", type=int, default=100, help="Requests per level")
    parser.add_argument("--timeout", type=float, default=120.0, help="Request timeout (s)")

    args = parser.parse_args()

    levels = [int(x.strip()) for x in args.levels.split(",")]

    run_stress_test(
        base_url=args.url,
        levels=levels,
        requests_per_level=args.requests,
        timeout=args.timeout
    )
