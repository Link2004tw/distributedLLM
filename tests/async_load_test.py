import asyncio
import httpx
import time

LB = "http://127.0.0.1:8000"


async def send_async(client, i):
    try:
        start = time.time()
        resp = await client.post(f"{LB}/query", json={"query": f"test {i}", "top_k": 1})
        lat = (time.time() - start) * 1000
        ok = resp.status_code == 200
        return (lat, ok, resp.json().get("worker_id") if ok else None)
    except Exception as e:
        return (0, False, str(e)[:30])


async def run_level(total, concurrency):
    print(f"\nRunning {total} requests @ {concurrency} concurrency...")
    async with httpx.AsyncClient(timeout=60.0, limits=httpx.Limits(max_connections=concurrency*2)) as client:
        tasks = [send_async(client, i) for i in range(total)]
        results = await asyncio.gather(*tasks)

    ok = [r for r in results if r[1]]
    fail = [r for r in results if not r[1]]
    lats = sorted([r[0] for r in ok])
    workers = {}
    for _, ok_fl, wid in results:
        if ok_fl:
            workers[wid] = workers.get(wid, 0) + 1

    print(f"  {len(ok)}/{total} OK")
    if lats:
        p95_idx = min(int(len(lats) * 0.95), len(lats)-1)
        p99_idx = min(int(len(lats) * 0.99), len(lats)-1)
        print(f"  Latency: mean={sum(lats)/len(lats):.0f}ms, "
              f"P95={lats[p95_idx]:.0f}ms, max={max(lats):.0f}ms")
    print(f"  Workers: {dict(sorted(workers.items(), key=lambda x: -x[1]))}")
    return len(ok), total, lats


async def main():
    print("Checking services...")
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            r = await client.get(f"{LB}/health")
            print(f"  LB: {r.json()}")
    except Exception as e:
        print(f"  LB unreachable: {e}")
        return

    results = []
    results.append(await run_level(100, 20))
    await asyncio.sleep(2)
    results.append(await run_level(250, 25))
    await asyncio.sleep(2)
    results.append(await run_level(500, 30))
    await asyncio.sleep(2)
    results.append(await run_level(1000, 40))

    print(f"\n{'='*60}")
    print("SUMMARY")
    print(f"{'Level':>6} {'Success':>8} {'Total':>6}")
    for i, (ok, total, lats) in enumerate(results):
        print(f"  {100*(i+1):>4}   {ok:>6}/{total}")
    print(f"{'='*60}")


if __name__ == "__main__":
    asyncio.run(main())