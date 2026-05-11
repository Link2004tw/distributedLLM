import httpx
import time
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed

LB = "http://127.0.0.1:8000"

print("Starting services check...")
r = httpx.get(f"{LB}/health", timeout=5)
print(f"LB health: {r.json()}")

r = httpx.get(f"{LB}/workers", timeout=5)
workers = r.json()["workers"]
print(f"Workers: {len(workers)} total, "
      f"{sum(1 for w in workers if w.get('healthy'))} healthy")

# Test sequential
print("\nSequential test (10 requests)...")
for i in range(10):
    start = time.time()
    r = httpx.post(f"{LB}/query", json={"query": f"test {i}", "top_k": 1}, timeout=60)
    elapsed = (time.time() - start) * 1000
    if r.status_code == 200:
        print(f"  {i+1}: OK in {elapsed:.0f}ms")
    else:
        print(f"  {i+1}: FAIL {r.status_code}")

# Test concurrent
print("\nConcurrent test (20 requests @ 5 concurrency)...")
results = []
def send(i):
    start = time.time()
    r = httpx.post(f"{LB}/query", json={"query": f"concurrent {i}", "top_k": 1}, timeout=90)
    elapsed = time.time() - start
    return r.status_code, elapsed, r.json().get("worker_id") if r.status_code == 200 else None

start = time.time()
with ThreadPoolExecutor(max_workers=5) as ex:
    futures = [ex.submit(send, i) for i in range(20)]
    for f in as_completed(futures):
        results.append(f.result())
total = time.time() - start

ok = [r for r in results if r[0] == 200]
print(f"  {len(ok)}/20 succeeded in {total:.1f}s ({20/total:.1f} req/s)")
for status, elapsed, wid in sorted(results, key=lambda x: x[1]):
    print(f"    {status} in {elapsed*1000:.0f}ms" + (f" -> {wid}" if wid else ""))

# Test higher concurrency
print("\nHigher concurrency test (50 requests @ 10 concurrency)...")
results = []
start = time.time()
with ThreadPoolExecutor(max_workers=10) as ex:
    futures = [ex.submit(send, i) for i in range(50)]
    for f in as_completed(futures):
        results.append(f.result())
total = time.time() - start

ok = [r for r in results if r[0] == 200]
failed = [r for r in results if r[0] != 200]
lats = [r[1] * 1000 for r in ok]
lats.sort()
print(f"  {len(ok)}/50 succeeded in {total:.1f}s ({50/total:.1f} req/s)")
if lats:
    p95 = lats[int(0.95 * len(lats)) - 1]
    print(f"  P95 latency: {p95:.0f}ms")

workers_used = {}
for r in ok:
    if r[2]:
        workers_used[r[2]] = workers_used.get(r[2], 0) + 1
print(f"  Workers: {workers_used}")