import httpx, time, statistics, threading
from concurrent.futures import ThreadPoolExecutor, as_completed


LB_URL = "http://127.0.0.1:8000"


def run_level(name, total, concurrency, warmup=5):
    print(f"\n{'='*60}")
    print(f"LEVEL {name}: {total} requests @ {concurrency} concurrency")
    print(f"{'='*60}")

    # Warmup
    client = httpx.Client(timeout=120)
    for i in range(warmup):
        try:
            client.post(f"{LB_URL}/query", json={"query": f"warmup {i}", "top_k": 1}, timeout=60)
        except Exception:
            pass

    # Test
    results = []
    lock = threading.Lock()

    def send(i):
        start = time.perf_counter()
        try:
            r = client.post(f"{LB_URL}/query", json={"query": f"load test {i}", "top_k": 1}, timeout=120)
            latency = (time.perf_counter() - start) * 1000
            ok = r.status_code == 200
            worker = r.json().get("worker_id") if ok else None
            return latency, ok, worker, None
        except httpx.TimeoutException:
            return (time.perf_counter() - start) * 1000, False, None, "timeout"
        except Exception as e:
            return (time.perf_counter() - start) * 1000, False, None, str(e)

    start_time = time.perf_counter()
    with ThreadPoolExecutor(max_workers=concurrency) as ex:
        futures = [ex.submit(send, i) for i in range(total)]
        for f in as_completed(futures):
            results.append(f.result())

    total_time = time.perf_counter() - start_time
    client.close()

    # Analyze
    successful = [(lat, wid) for lat, ok, wid, err in results if ok]
    failed = [err for lat, ok, wid, err in results if not ok]

    latencies = [lat for lat, ok, wid, err in results if ok]
    latencies.sort()

    def pct(arr, p):
        if not arr:
            return 0
        idx = int((p / 100) * len(arr))
        idx = min(max(1, idx), len(arr) - 1)
        return arr[idx - 1]

    workers = {}
    for lat, wid in successful:
        workers[wid] = workers.get(wid, 0) + 1

    print(f"  Total:   {total}")
    print(f"  Success: {len(successful)}, Failed: {len(failed)}")
    print(f"  Time:    {total_time:.1f}s")
    print(f"  RPS:     {total / total_time:.2f} req/s")
    print(f"  Latency:")
    print(f"    Mean: {statistics.mean(latencies):.0f}ms")
    print(f"    Min:  {min(latencies):.0f}ms")
    print(f"    Max:  {max(latencies):.0f}ms")
    print(f"    P50:  {pct(latencies, 50):.0f}ms")
    print(f"    P75:  {pct(latencies, 75):.0f}ms")
    print(f"    P90:  {pct(latencies, 90):.0f}ms")
    print(f"    P95:  {pct(latencies, 95):.0f}ms")
    print(f"    P99:  {pct(latencies, 99):.0f}ms")

    if workers:
        print(f"  Worker distribution:")
        for wid, cnt in sorted(workers.items(), key=lambda x: -x[1]):
            pct_v = cnt / len(successful) * 100
            print(f"    {wid}: {cnt} ({pct_v:.1f}%)")

    if failed:
        errors = {}
        for err in failed:
            errors[err] = errors.get(err, 0) + 1
        print(f"  Errors:")
        for err, cnt in sorted(errors.items(), key=lambda x: -x[1]):
            print(f"    {err}: {cnt}")

    error_rate = len(failed) / total * 100
    status = "[PASS]" if len(successful) >= total * 0.95 else "[FAIL]" if len(successful) < total * 0.5 else "[WARN]"
    print(f"  {status} Error rate: {error_rate:.1f}%")

    return {
        "name": name, "total": total, "concurrency": concurrency,
        "successful": len(successful), "failed": len(failed),
        "error_rate": round(error_rate, 2),
        "duration_s": round(total_time, 2),
        "throughput_rps": round(total / total_time, 2),
        "latency_mean_ms": round(statistics.mean(latencies), 2),
        "latency_p50_ms": round(pct(latencies, 50), 2),
        "latency_p95_ms": round(pct(latencies, 95), 2),
        "latency_p99_ms": round(pct(latencies, 99), 2),
        "worker_distribution": workers,
    }


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default=LB_URL)
    args = parser.parse_args()

    # Set hybrid strategy
    try:
        httpx.post(f"{args.url}/strategy", json={"strategy": "hybrid"}, timeout=10)
    except Exception:
        pass

    print(f"\nTarget: {args.url}")
    print(f"Strategy: hybrid")

    results = []

    results.append(run_level(100, 100, 20))
    time.sleep(3)

    results.append(run_level(250, 250, 25))
    time.sleep(3)

    results.append(run_level(500, 500, 30))
    time.sleep(3)

    results.append(run_level(1000, 1000, 40))

    # Summary
    print("\n" + "=" * 80)
    print("LOAD TEST SUMMARY")
    print("=" * 80)
    print(f"{'Level':>6} {'Req':>5} {'Conc':>5} {'Succ':>5} {'Fail':>5} "
          f"{'RPS':>7} {'P50ms':>8} {'P95ms':>8} {'P99ms':>8} {'Err%':>6}")
    print("-" * 80)
    for r in results:
        print(f"{r['name']:>6} {r['total']:>5} {r['concurrency']:>5} "
              f"{r['successful']:>5} {r['failed']:>5} "
              f"{r['throughput_rps']:>7.1f} "
              f"{r['latency_p50_ms']:>7.0f} {r['latency_p95_ms']:>7.0f} {r['latency_p99_ms']:>7.0f} "
              f"{r['error_rate']:>5.1f}%")
    print("=" * 80)


if __name__ == "__main__":
    main()