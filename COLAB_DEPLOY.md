# Google Colab Deployment Guide

How to run the Distributed LLM Inference System inside **Google Colab** using its free T4 GPU.

---

## 1. What Colab Gives You

| Resource | Free Tier |
|---|---|
| GPU | NVIDIA T4 (16GB VRAM) — sometimes K80 or T4 |
| RAM | ~12 GB system RAM |
| Disk | ~78 GB ephemeral |
| Session limit | 12 hours max |
| Idle timeout | ~90 min inactivity |
| Public IP | No — HTTP ports not exposed to internet |

**Limits vs. Cloud VMs:**
- Cannot serve external HTTP traffic (no public IP)
- All components run on **one machine** (no multi-node)
- Session stops when browser closes
- File system is ephemeral (use Google Drive for persistence)

**What you CAN do:**
- Run all components (LB, Master, 4 Workers) as background processes
- Run the load generator from the same Colab notebook
- Collect performance benchmarks and download results

---

## 2. Quick Start (Copy-Paste into Colab)

### Cell 1 — Install System Dependencies

```python
import os
import sys
import subprocess
import time
import threading
from IPython.display import clear_output

# Install Ollama
!curl -fsSL https://ollama.com/install.sh | sh

# Start Ollama in background
subprocess.Popen(["ollama", "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
time.sleep(3)

# Pull models
!ollama pull smollm2:135m
!ollama pull nomic-embed-text
```

### Cell 2 — Install Python Dependencies

```python
!pip install -q fastapi uvicorn pydantic httpx langchain langchain-ollama langchain-chroma chromadb sentence-transformers jinja2

# Clone your repo (or upload)
!git clone <your-repo-url> distributedLLM
os.chdir("distributedLLM")

# Or upload from Google Drive
# from google.colab import drive
# drive.mount("/content/drive")
# !cp -r /content/drive/MyDrive/distributedLLM .
# os.chdir("distributedLLM")
```

### Cell 3 — Ingest RAG Documents

```python
!python ingest.py
```

### Cell 4 — Start System Components

```python
import subprocess
import time
import signal
import os

processes = []

def start_component(name, cmd, env=None):
    merged_env = os.environ.copy()
    if env:
        merged_env.update(env)
    proc = subprocess.Popen(
        cmd, env=merged_env, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True
    )
    processes.append(proc)
    print(f"[{name}] Started PID={proc.pid}")
    return proc

# Kill any lingering processes first
subprocess.run("pkill -f uvicorn", shell=True)
time.sleep(1)

print("Starting Master Node...")
start_component(
    "Master",
    ["uvicorn", "master.monitor:app", "--host", "0.0.0.0", "--port", "9000"]
)
time.sleep(2)

print("Starting Workers (x4)...")
for i in range(1, 5):
    start_component(
        f"Worker-{i}",
        ["uvicorn", "workers.worker:app", "--host", "0.0.0.0", "--port", f"800{i}"],
        env={
            "WORKER_ID": f"worker-{i}",
            "PORT": f"800{i}",
            "MASTER_NODE_URL": "http://localhost:9000",
            "OLLAMA_URL": "http://localhost:11434",
            "MAX_CONCURRENT_TASKS": "8",
            "BACKPRESSURE_QUEUE_SIZE": "100"
        }
    )
    time.sleep(1.5)

print("Starting Load Balancer...")
start_component(
    "LB",
    ["uvicorn", "lb.load_balancer:app", "--host", "0.0.0.0", "--port", "8000"],
    env={
        "MASTER_NODE_URL": "http://localhost:9000",
        "LB_PORT": "8000"
    }
)
time.sleep(3)
```

### Cell 5 — Verify All Services Are Running

```python
import httpx

services = [
    ("Master", 9000, "/health"),
    ("Worker-1", 8001, "/health"),
    ("Worker-2", 8002, "/health"),
    ("Worker-3", 8003, "/health"),
    ("Worker-4", 8004, "/health"),
    ("LB", 8000, "/health"),
]

client = httpx.Client(timeout=5)
for name, port, path in services:
    try:
        r = client.get(f"http://localhost:{port}{path}")
        print(f"[OK] {name} — port {port} — {r.status_code}")
    except Exception as e:
        print(f"[FAIL] {name} — port {port} — {e}")

# Check workers registered with master
r = client.get("http://localhost:9000/workers")
print(f"\nWorkers registered with Master: {len(r.json()['workers'])}")
for w in r.json()["workers"]:
    print(f"  {w['worker_id']} — port {w['port']} — healthy={w['healthy']}")

client.close()
```

### Cell 6 — Run a Quick Smoke Test

```python
import httpx, json

client = httpx.Client(timeout=120)
payload = {"query": "What is distributed computing?", "top_k": 1}

# Direct to LB
r = client.post("http://localhost:8000/query", json=payload)
print(f"Status: {r.status_code}")
data = r.json()
print(f"Worker: {data.get('worker_id')}")
print(f"Answer: {data.get('answer', '')[:200]}...")
print(f"Latency: {data.get('latency_ms', 0):.1f}ms")
print(f"Cache hit: {data.get('cache_hit', False)}")
client.close()
```

### Cell 7 — Run Load Test

```python
!python client/load_generator.py \
  --url http://localhost:8000 \
  --requests 500 \
  --concurrency 50 \
  --timeout 300 \
  --warmup 5
```

### Cell 8 — Check Performance Stats

```python
import httpx

client = httpx.Client(timeout=5)
r = client.get("http://localhost:8000/stats")
stats = r.json()

print("=== Load Balancer Stats ===")
print(f"Total requests:   {stats['total_requests']}")
print(f"Successful:       {stats['successful_requests']}")
print(f"Failed:           {stats['failed_requests']}")
print(f"Error rate:       {stats['error_rate_percent']}%")
print(f"Healthy workers:  {stats['healthy_workers']}/{stats['total_workers']}")
print(f"Pending:          {stats['pending_requests']}")
print()

print("=== Latency ===")
lat = stats['latency']
print(f"Count:  {lat['count']}")
print(f"Avg:    {lat['avg_ms']:.1f}ms")
print(f"P50:    {lat['p50_ms']:.1f}ms")
print(f"P75:    {lat['p75_ms']:.1f}ms")
print(f"P90:    {lat['p90_ms']:.1f}ms")
print(f"P95:    {lat['p95_ms']:.1f}ms")
print(f"P99:    {lat['p99_ms']:.1f}ms")
print()

print("=== Per-Worker Throughput ===")
for wid, count in stats['per_worker_throughput'].items():
    print(f"  {wid}: {count} requests")
client.close()
```

### Cell 9 — Check GPU Utilization

```python
import subprocess
result = subprocess.run(
    ["nvidia-smi", "--query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu",
     "--format=csv,noheader,nounits"],
    capture_output=True, text=True
)
print(result.stdout)
```

---

## 3. Tuning for Best Colab Performance

### Edit These Settings Before Starting

**`workers/worker.py`** — increase concurrency:
```python
MAX_CONCURRENT_TASKS = 8       # was 4 — utilizes Colab's 4 CPU cores
BACKPRESSURE_QUEUE_SIZE = 100  # was 50
CACHE_SIZE = 1000              # was 500
BATCH_SIZE = 16                # was 10
```

**`lb/load_balancer.py`** — remove bottleneck:
```python
MAX_CONCURRENT_REQUESTS = 2000  # was 50
```

Or pass via environment in Cell 4:
```python
env={
    "MAX_CONCURRENT_TASKS": "8",
    "BACKPRESSURE_QUEUE_SIZE": "100"
}
```

### Model Choice on T4 (16GB)

| Model | Size | Speed on T4 | Quality |
|---|---|---|---|
| **smollm2:135m** | 270 MB | ~50ms/inference | Low |
| **smollm2:360m** | 500 MB | ~100ms/inference | Fair |
| **qwen2.5:0.5b** | 397 MB | ~80ms/inference | Good |
| **qwen2.5:1.5b** | 936 MB | ~200ms/inference | Better |
| **llama3.2:3b** | 2.0 GB | ~500ms/inference | Best |
| **qwen2.5:7b** | 4.4 GB | ~1.5s/inference | Excellent |

For load testing: use **smollm2:135m** or **qwen2.5:0.5b**.
For demo quality: use **llama3.2:3b** or **qwen2.5:7b**.

### Expected Performance

| Configuration | Req/sec | P50 Latency | P95 Latency |
|---|---|---|---|
| 4 workers, smollm2:135m | ~3-5 req/s | ~2s | ~8s |
| 4 workers, qwen2.5:0.5b | ~2-3 req/s | ~3s | ~12s |
| 4 workers, llama3.2:3b | ~0.5-1 req/s | ~8s | ~20s |
| 8 workers (simulated), smollm2:135m | ~6-10 req/s | ~1s | ~5s |

> *Colab's single T4 is the hard limit. Multiple workers share the same GPU — they don't multiply throughput, they handle concurrent requests better.*

---

## 4. Fault Tolerance Demo (Within Colab)

```python
import httpx, time

def send_requests(count=20):
    client = httpx.Client(timeout=120)
    success, fail = 0, 0
    for i in range(count):
        try:
            r = client.post("http://localhost:8000/query",
                json={"query": f"test {i}", "top_k": 1})
            if r.status_code == 200: success += 1
            else: fail += 1
        except: fail += 1
    client.close()
    return success, fail

# Step 1: Baseline
print("=== Baseline ===")
s, f = send_requests(10)
print(f"  Success: {s}/10")

# Step 2: Check workers
client = httpx.Client(timeout=5)
workers_before = client.get("http://localhost:9000/workers").json()["workers"]
print(f"\nWorkers before: {[w['worker_id'] for w in workers_before]}")
client.close()

# Step 3: Kill a worker (simulated by shutting one port)
import subprocess
subprocess.run("pkill -f \"uvicorn.*8003\"", shell=True)
time.sleep(3)

# Step 4: Requests during failure
print("\n=== During Worker Failure ===")
s, f = send_requests(20)
print(f"  Success: {s}/20 (system kept working)")

# Step 5: Check LB health
client = httpx.Client(timeout=5)
lb_workers = client.get("http://localhost:8000/workers").json()["workers"]
print(f"\nLB reports: {sum(1 for w in lb_workers if w['healthy'])}/{len(lb_workers)} healthy")
client.close()

# Step 6: Restart worker
print("\n=== Restarting Worker ===")
start_component(
    "Worker-3",
    ["uvicorn", "workers.worker:app", "--host", "0.0.0.0", "--port", "8003"],
    env={"WORKER_ID": "worker-3", "PORT": "8003",
         "MASTER_NODE_URL": "http://localhost:9000",
         "OLLAMA_URL": "http://localhost:11434"}
)
time.sleep(5)

# Step 7: Verify recovery
client = httpx.Client(timeout=5)
workers_after = client.get("http://localhost:9000/workers").json()["workers"]
print(f"\nWorkers after restart: {len(workers_after)}")
client.close()
```

---

## 5. Persistent Storage with Google Drive

```python
from google.colab import drive
drive.mount("/content/drive")

# Symlink chroma_db to Drive for persistence
import os
if os.path.exists("/content/drive/MyDrive/distributedLLM/chroma_db"):
    !rm -rf chroma_db
    !ln -s /content/drive/MyDrive/distributedLLM/chroma_db chroma_db
else:
    !cp -r chroma_db /content/drive/MyDrive/distributedLLM/
```

---

## 6. Stop Everything (End of Session)

```python
# Kill all background processes
import subprocess
subprocess.run("pkill -f uvicorn", shell=True)
subprocess.run("pkill -f ollama", shell=True)
print("All services stopped")
```

---

## 7. Running Online Demo with Ngrok

If you need to expose the LB to external access (e.g., for a demo video):

```python
!pip install -q pyngrok

from pyngrok import ngrok

# Start ngrok tunnel to LB
public_url = ngrok.connect(8000, "http")
print(f"Public URL: {public_url}")
print(f"Send queries to: {public_url}/query")

# Example: curl from outside
# curl -X POST https://abc123.ngrok.io/query \
#   -H "Content-Type: application/json" \
#   -d '{"query":"What is distributed computing?","top_k":1}'
```

---

## 8. Comparison: Colab vs Cloud VMs

| Aspect | Google Colab | Cloud GPU VMs |
|---|---|---|
| GPU | 1x T4 (shared) | Dedicated T4/A100 |
| Session | 12h max | Unlimited |
| Multi-node | ❌ Single machine | ✅ Scale to 64+ workers |
| Public endpoint | Ngrok (slow) | Direct public IP |
| True 1000 concurrent | ❌ Not possible | ✅ With 16+ workers |
| Queue architecture | Not needed | Required for scale |
| Cost | Free | $0.35-$3.50/hr |
| Best for | Dev, testing, demo | Production load test |

**Colab is ideal for:** development, unit testing, fault tolerance demos, small load tests (up to 500 requests).

**For 1000 concurrent users:** You still need multi-GPU deployment (cloud VMs or multi-node setup).
