import httpx
import time
import statistics

LB = "http://127.0.0.1:8000"

print("Quick load test: 50 requests @ 5 concurrency")

# Single client, 5 threads
results = []

def send(i):
    client = httpx.Client(timeout=60)
    try:
        start = time.time()
        resp = client.post(LB + "/query", json={"query": f"test {i}", "top_k": 1})
        lat = (time.time() - start) * 1000
        return (lat, resp.status_code == 200, resp.json().get("worker_id") if resp.status_code == 200 else None)
    except Exception as e:
        return (0, False, str(e)[:30])
    finally:
        client.close()

import threading
lock = threading.Lock()
workers = {}
errors = {}
all_results = []

def worker_fn(i):
    lat, ok, info = send(i)
    with lock:
        all_results.append((lat, ok, info))
        if ok:
            workers[info] = workers.get(info, 0) + 1
        else:
            errors[info] = errors.get(info, 0) + 1

threads = []
for i in range(50):
    t = threading.Thread(target=worker_fn, args=(i,))
    threads.append(t)
    t.start()
    if len(threads) >= 5:
        for tt in threads:
            tt.join()
        threads = []
for tt in threads:
    tt.join()

ok_results = [r for r in all_results if r[1]]
fail_results = [r for r in all_results if not r[1]]
lats = sorted([r[0] for r in ok_results])

print(f"\nResults: {len(ok_results)}/50 succeeded")
print(f"Workers: {dict(sorted(workers.items(), key=lambda x: -x[1]))}")
if lats:
    print(f"Latency: mean={statistics.mean(lats):.0f}ms, P95={lats[int(len(lats)*0.95)-1]:.0f}ms, max={max(lats):.0f}ms")
if errors:
    print(f"Errors: {errors}")