import httpx, time

# Quick sanity test
print("Testing single request...")
r = httpx.post(
    'http://127.0.0.1:8000/query',
    json={'query': 'test', 'top_k': 1},
    timeout=60
)
print(f"Status: {r.status_code}")
if r.status_code == 200:
    data = r.json()
    print(f"Latency: {data.get('latency_ms', 0):.0f}ms")
    print(f"Worker: {data.get('worker_id')}")
else:
    print(f"Error: {r.text}")

# Check LB stats
r = httpx.get('http://127.0.0.1:8000/stats', timeout=5)
print(f"\nLB Stats: {r.json()}")

# Check workers
r = httpx.get('http://127.0.0.1:8000/workers', timeout=5)
workers = r.json()['workers']
healthy = [w for w in workers if w.get('healthy')]
print(f"Workers: {len(workers)} total, {len(healthy)} healthy")
for w in workers[:4]:
    print(f"  {w['worker_id']}: healthy={w.get('healthy')}, "
          f"connections={w.get('active_connections')}, "
          f"latency={w.get('avg_latency_ms', 0):.0f}ms")