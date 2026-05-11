import subprocess
import time
import json

print("Testing Ollama direct inference...")
start = time.time()
r = subprocess.run([
    'curl', '-s', '-X', 'POST', 'http://localhost:11434/api/generate',
    '-H', 'Content-Type: application/json',
    '-d', '{"model":"smollm2:135m","prompt":"What is 2+2?","stream":false}'
], capture_output=True, text=True)
elapsed = time.time() - start

print(f"Ollama direct: {elapsed:.1f}s, returncode={r.returncode}")
if r.returncode == 0:
    try:
        data = json.loads(r.stdout)
        print(f"Response: {data.get('response','')[:100]}")
    except:
        print(f"Raw: {r.stdout[:200]}")
else:
    print(f"Error: {r.stderr[:200]}")

print("\nTesting worker directly...")
import httpx
start = time.time()
try:
    r = httpx.post('http://127.0.0.1:8001/query', json={'query': 'What is 2+2?', 'top_k': 1}, timeout=90)
    elapsed = time.time() - start
    print(f"Worker direct: {elapsed:.1f}s, status={r.status_code}")
    if r.status_code == 200:
        data = r.json()
        print(f"Latency: {data.get('latency_ms',0):.0f}ms, Cache: {data.get('cache_hit')}")
        print(f"Answer: {data.get('answer','')[:100]}")
except Exception as e:
    elapsed = time.time() - start
    print(f"Worker direct: FAILED after {elapsed:.1f}s - {e}")

print("\nTesting LB...")
start = time.time()
try:
    r = httpx.post('http://127.0.0.1:8000/query', json={'query': 'What is 2+2?', 'top_k': 1}, timeout=90)
    elapsed = time.time() - start
    print(f"LB: {elapsed:.1f}s, status={r.status_code}")
    if r.status_code == 200:
        data = r.json()
        print(f"Latency: {data.get('latency_ms',0):.0f}ms, Worker: {data.get('worker_id')}")
except Exception as e:
    elapsed = time.time() - start
    print(f"LB: FAILED after {elapsed:.1f}s - {e}")