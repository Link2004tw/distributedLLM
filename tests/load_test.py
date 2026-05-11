import httpx
import time
import statistics
import threading

LB = "http://127.0.0.1:8000"


def run_test(name, total, concurrency, warmup=3):
    print(f"\n{'='*60}")
    print(f"{name}: {total} requests @ {concurrency} concurrency")
    print(f"{'='*60}")

    results = []
    errors = {}
    workers = {}
    lock = threading.Lock()

    def send(i):
        client = httpx.Client(timeout=90)
        try:
            start = time.time()
            resp = client.post(f"{LB}/query", json={"query": f"load test {i}", "top_k": 1})
            latency = (time.time() - start) * 1000
            if resp.status_code == 200:
                data = resp.json()
                wid = data.get("worker_id", "unknown")
                with lock:
                    workers[wid] = workers.get(wid, 0) + 1
                return latency, True, wid, None
            else:
                with lock:
                    errors[f"HTTP {resp.status_code}"] = errors.get(f"HTTP {resp.status_code}", 0) + 1
                return latency, False, None, f"HTTP {resp.status_code}"
        except httpx.TimeoutException:
            with lock:
                errors["timeout"] = errors.get("timeout", 0) + 1
            return 0, False, None, "timeout"
        except Exception as e:
            with lock:
                errors[str(type(e).__name__)] = errors.get(str(type(e).__name__), 0) + 1
            return 0, False, None, str(e)
        finally:
            client.close()

    # Warmup
    print(f"  Warming up ({warmup} requests)...")
    warmup_client = httpx.Client(timeout=60)
    for i in range(warmup):
        try:
            warmup_client.post(f"{LB}/query", json={"query": f"warmup {i}", "top_k": 1})
        except Exception:
            pass
    warmup_client.close()

    # Test
    print(f"  Running {total} requests...")
    start_time = time.time()
    with threading.ThreadPoolExecutor(max_workers=concurrency) as ex:
        futures = [ex.submit(send, i) for i in range(total)]
        for f in futures:
            results.append(f.result())

    total_time = time.time() - start_time

    # Analyze
    ok = [r for r in results if r[1]]
    fail = [r for r in results if not r[1]]
    latencies = [r[0] for r in ok]

    print(f"\n  Results:")
    print(f"    Time:     {total_time:.1f}s")
    print(f"    Throughput: {total / total_time:.1f} req/s")
    print(f"    Success:  {len(ok)}/{total} ({len(ok)/total*100:.0f}%)")
    print(f"    Failed:   {len(fail)}")

    if latencies:
        latencies.sort()
        p95_idx = int(len(latencies) * 0.95)
        p99_idx = int(len(latencies) * 0.99)
        print(f"    Latency:  mean={statistics.mean(latencies):.0f}ms, "
              f"min={min(latencies):.0f}ms, max={max(latencies):.0f}ms")
        print(f"    P95: {latencies[min(p95_idx, len(latencies)-1)]:.0f}ms")
        print(f"    P99: {latencies[min(p99_idx, len(latencies)-1)]:.0f}ms")

    if workers:
        print(f"    Workers:  {dict(sorted(workers.items(), key=lambda x: -x[1]))}")

    if errors:
        print(f"    Errors:")
        for err, cnt in sorted(errors.items(), key=lambda x: -x[1]):
            print(f"      {err}: {cnt}")

    return {
        "name": name, "total": total, "concurrency": concurrency,
        "successful": len(ok), "failed": len(fail),
        "duration_s": round(total_time, 2),
        "throughput_rps": round(total / total_time, 2),
        "latency_mean_ms": round(statistics.mean(latencies), 1) if latencies else 0,
        "latency_p95_ms": round(latencies[min(p95_idx, len(latencies)-1)], 1) if latencies else 0,
        "latency_p99_ms": round(latencies[min(p99_idx, len(latencies)-1)], 1) if latencies else 0,
    }


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", default=LB)
    args = parser.parse_args()

    # Check services
    print("Checking services...")
    try:
        r = httpx.get(f"{args.url}/health", timeout=5)
        print(f"LB: {r.json()}")
    except Exception as e:
        print(f"LB unreachable: {e}")
        return

    r = httpx.get(f"{args.url}/workers", timeout=5)
    workers = r.json()["workers"]
    print(f"Workers: {len(workers)} ({', '.join(w['worker_id'] for w in workers[:4])}"
          f"{'...' if len(workers) > 4 else ''})")

    results = []
    results.append(run_test("Level 100", 100, 20))
    time.sleep(2)

    results.append(run_test("Level 250", 250, 30))
    time.sleep(2)

    results.append(run_test("Level 500", 500, 40))
    time.sleep(2)

    results.append(run_test("Level 1000", 1000, 50))

    # Summary table
    print("\n" + "=" * 80)
    print("LOAD TEST SUMMARY")
    print("=" * 80)
    print(f"{'Level':>8} {'Requests':>8} {'Conc':>5} {'Success':>8} {'Failed':>7} "
          f"{'RPS':>8} {'P95ms':>8} {'P99ms':>8}")
    print("-" * 80)
    for r in results:
        print(f"{r['name']:>8} {r['total']:>8} {r['concurrency']:>5} "
              f"{r['successful']:>8} {r['failed']:>7} "
              f"{r['throughput_rps']:>8.1f} "
              f"{r['latency_p95_ms']:>7.0f} {r['latency_p99_ms']:>7.0f}")
    print("=" * 80)


if __name__ == "__main__":
    main()