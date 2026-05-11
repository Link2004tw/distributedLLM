import httpx
import time

LB = "http://127.0.0.1:8000"
WORKER = "http://127.0.0.1:8001"

print("Testing worker directly (3 requests)...")
for i in range(3):
    client = httpx.Client(timeout=60)
    try:
        start = time.time()
        r = client.post(f"{WORKER}/query", json={"query": f"test {i}", "top_k": 1})
        elapsed = time.time() - start
        print(f"  Worker {i+1}: {r.status_code} in {elapsed*1000:.0f}ms -> {r.json().get('worker_id')}")
    except Exception as e:
        print(f"  Worker {i+1}: FAILED - {e}")
    finally:
        client.close()

print("\nTesting LB directly (3 requests)...")
for i in range(3):
    client = httpx.Client(timeout=60)
    try:
        start = time.time()
        r = client.post(f"{LB}/query", json={"query": f"test {i}", "top_k": 1})
        elapsed = time.time() - start
        print(f"  LB {i+1}: {r.status_code} in {elapsed*1000:.0f}ms -> {r.json().get('worker_id') if r.status_code == 200 else 'FAIL'}")
    except Exception as e:
        print(f"  LB {i+1}: FAILED - {e}")
    finally:
        client.close()