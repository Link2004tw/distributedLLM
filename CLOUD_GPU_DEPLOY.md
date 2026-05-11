# Cloud GPU Deployment Guide

How to run the Distributed LLM Inference System across **multiple cloud GPU instances** for real distributed computing and handling **1000 concurrent users**.

---

## 1. Choose a Provider

| Provider | GPU | Cost/hr | Credits / Free Trial | Best For |
|---|---|---|---|---|
| **Google Cloud** | T4 (16GB), V100, A100 | $0.35-$3.50 | **$300 free** (90 days) | Full distributed test |
| **Azure for Students** | NC6s (K80/T4) | $0.90 | **$100 free credits** | Student deployment |
| **Lambda Labs** | A100, H100 | $1.10-$3.78 | No free tier, on-demand | Production load test |
| **Vast.ai** | RTX 3090/4090, A6000 | $0.20-$0.70 | No free tier | Cheap multi-GPU |
| **RunPod** | RTX 3090, A100 | $0.21-$2.69 | No free tier | Serverless inference |
| **Paperspace** | RTX 4000, A100 | $0.29-$2.30 | Free tier (limited) | Quick prototyping |
| **CoreWeave** | H100, B200 | $2.69-$5.98 | No free tier | High-scale production |

### Recommended Setup for 1000 Concurrent Users

| Setup | Nodes | GPUs/Node | Est. Cost/hr |
|---|---|---|---|
| **Minimum viable** | 1 LB + 1 Master + 4 Workers (all on 1 instance) | 1x T4 | $0.35 (on GCP) |
| **Small scale** | 1 LB/Master + 4 Workers (on 2 instances) | 1x T4 each | $0.70 |
| **Medium scale** | 1 LB/Master + 8 Workers (on 4 instances) | 1x T4 each | $1.40 |
| **Full scale** | 1 LB + 1 Master + 16 Workers (on 8 instances) | 1x T4 each | $3.15 |

---

## 2. System Architecture (Multi-Node)

```
                           Internet
                              |
               ┌──────────────┴──────────────┐
               │   Load Balancer (port 8000)  │
               │   cloud-gpu-lb:8000          │
               └──────────────┬───────────────┘
                              │
          ┌───────────────────┼───────────────────┐
          │                   │                   │
  ┌───────┴───────┐   ┌──────┴───────┐   ┌───────┴───────┐
  │  Worker Node 1 │   │  Worker Node 2│...│  Worker Node N│
  │  port 8001     │   │  port 8001    │   │  port 8001    │
  │  (GPU: T4)     │   │  (GPU: T4)    │   │  (GPU: T4)    │
  │  Ollama:11434  │   │  Ollama:11434 │   │  Ollama:11434 │
  └───────┬───────┘   └──────┬───────┘   └───────┬───────┘
          │                   │                   │
          └───────────────────┼───────────────────┘
                              │
               ┌──────────────┴──────────────┐
               │      Master Node (9000)      │
               │  cloud-gpu-master:9000       │
               └─────────────────────────────┘
```

**Network flow:**
- **Clients** send requests to Load Balancer (public IP)
- **LB** routes to Workers (private/internal IPs)
- **Workers** register with Master (private/internal IP)
- **Master** monitors Worker health and notifies LB
- **Workers** each run local Ollama on the same instance

---

## 3. Instance Setup (Run on Every GPU Node)

### 3.1 Spin Up Instances

**Google Cloud example** (repeat for each node):
```bash
# Create GPU instance with T4
gcloud compute instances create worker-1 \
    --zone=us-central1-a \
    --accelerator=type=nvidia-tesla-t4,count=1 \
    --maintenance-policy=TERMINATE \
    --image-family=ubuntu-2204-lts \
    --image-project=ubuntu-os-cloud \
    --boot-disk-size=100GB \
    --machine-type=n1-standard-8
```

**Vast.ai / RunPod:** Select a template with PyTorch pre-installed and at least 16GB VRAM.

### 3.2 Install Dependencies

```bash
# Install NVIDIA drivers (if not pre-installed)
sudo apt update && sudo apt install -y nvidia-driver-545
sudo reboot

# Verify GPU
nvidia-smi

# Install Ollama
curl -fsSL https://ollama.com/install.sh | sh

# Install Python + project
sudo apt install -y python3.11 python3.11-venv git
git clone <your-repo-url> distributedLLM
cd distributedLLM
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 3.3 Pull Models (Run Once)

```bash
# Pull LLM model
ollama pull smollm2:135m

# Pull embedding model (for RAG)
ollama pull nomic-embed-text
```

On a **T4 (16GB)**, you can comfortably run models up to 7B parameters:
```bash
ollama pull qwen2.5:7b    # Better quality but slower
ollama pull llama3.2:3b   # Good balance
ollama pull smollm2:135m  # Fastest for load testing
```

### 3.4 Configure Ollama for Parallelism

```bash
sudo mkdir -p /etc/systemd/system/ollama.service.d
sudo tee /etc/systemd/system/ollama.service.d/override.conf << 'EOF'
[Service]
Environment="OLLAMA_NUM_PARALLEL=4"
Environment="OLLAMA_MAX_LOADED_MODELS=2"
Environment="OLLAMA_KEEP_ALIVE=5m"
Environment="OLLAMA_HOST=0.0.0.0:11434"
EOF

sudo systemctl daemon-reload
sudo systemctl restart ollama
```

---

## 4. Configuration for Multi-Node

### 4.1 Environment Variables Reference

| Variable | Purpose | Single-Machine | Multi-Node |
|---|---|---|---|
| `MASTER_NODE_URL` | Where workers register | `http://localhost:9000` | `http://<master-private-ip>:9000` |
| `LOAD_BALANCER_URL` | Where master sends failure alerts | `http://localhost:8000` | `http://<lb-private-ip>:8000` |
| `OLLAMA_URL` | Where Ollama runs | `http://localhost:11434` | `http://localhost:11434` (same node) |
| `WORKER_ID` | Unique worker name | `worker-1` | `worker-<region>-<num>` |
| `PORT` | Worker HTTP port | `8001` | `8001` |
| `MAX_CONCURRENT_TASKS` | Parallel LLM calls per worker | `4` | `16` (per GPU) |
| `BACKPRESSURE_QUEUE_SIZE` | Max queued before 503 | `50` | `200` |

### 4.2 IP Address Planning

```
Instance          Public IP        Private IP        Role
lb-master         34.XXX.YYY.1     10.128.0.10       Load Balancer + Master
worker-1          34.XXX.YYY.2     10.128.0.11       Worker + Ollama
worker-2          34.XXX.YYY.3     10.128.0.12       Worker + Ollama
worker-3          34.XXX.YYY.4     10.128.0.13       Worker + Ollama
worker-4          34.XXX.YYY.5     10.128.0.14       Worker + Ollama
```

### 4.3 Firewall / Security Group Rules

| Source | Destination | Port | Purpose |
|---|---|---|---|
| `0.0.0.0/0` | LB instance | `8000` | Client query endpoint |
| LB instance | Workers | `8001` | Route queries to workers |
| Workers | Master | `9000` | Worker registration + heartbeat |
| Master | LB | `8000` | Failure notifications |
| LB/Master IP | Your IP | `22` | SSH access |

---

## 5. Deploying the System

### 5.1 Transfer Code to All Instances

```bash
# From your local machine to each instance
scp -r distributedLLM user@<instance-ip>:~/
```

### 5.2 Set Up RAG Database (Once on One Node, Then Copy)

```bash
# On worker-1 only
cd ~/distributedLLM
source .venv/bin/activate

# Ingest documents
python ingest.py

# Copy ChromaDB to other workers
scp -r chroma_db user@worker-2:~/distributedLLM/
scp -r chroma_db user@worker-3:~/distributedLLM/
scp -r chroma_db user@worker-4:~/distributedLLM/
```

### 5.3 Start Components

**Terminal 1 — LB + Master instance:**
```bash
# Master Node
MASTER_NODE_URL=http://10.128.0.10:9000 \
LOAD_BALANCER_URL=http://10.128.0.10:8000 \
uvicorn master.monitor:app --host 0.0.0.0 --port 9000

# In a second terminal on the same instance:
LB_PORT=8000 \
MASTER_NODE_URL=http://10.128.0.10:9000 \
uvicorn lb.load_balancer:app --host 0.0.0.0 --port 8000
```

**Terminal 3 — Worker 1:**
```bash
WORKER_ID=worker-1 \
PORT=8001 \
MASTER_NODE_URL=http://10.128.0.10:9000 \
OLLAMA_URL=http://localhost:11434 \
MAX_CONCURRENT_TASKS=16 \
BACKPRESSURE_QUEUE_SIZE=200 \
uvicorn workers.worker:app --host 0.0.0.0 --port 8001
```

**Terminal 4 — Worker 2:**
```bash
WORKER_ID=worker-2 \
PORT=8001 \
MASTER_NODE_URL=http://10.128.0.10:9000 \
OLLAMA_URL=http://localhost:11434 \
MAX_CONCURRENT_TASKS=16 \
BACKPRESSURE_QUEUE_SIZE=200 \
uvicorn workers.worker:app --host 0.0.0.0 --port 8001
```

**Repeat for workers 3 and 4.**
> **Important**: Each worker uses port `8001` on its own instance. The master tracks them by `WORKER_ID`, not port.

### 5.4 Verify Everything Is Connected

```bash
# From your local machine:
# Check master sees workers
curl http://34.XXX.YYY.1:9000/workers

# Check LB sees workers
curl http://34.XXX.YYY.1:8000/workers

# Direct query (via LB)
curl -X POST http://34.XXX.YYY.1:8000/query \
  -H "Content-Type: application/json" \
  -d '{"query":"What is distributed computing?","top_k":1}'

# Check LB stats
curl http://34.XXX.YYY.1:8000/stats
```

---

## 6. Scaling for 1000 Concurrent Users

### 6.1 Configuration Changes

Edit these **before** starting any components:

**`workers/worker.py`:**
```python
MAX_CONCURRENT_TASKS = 16    # was 4 — utilize GPU parallelism
BACKPRESSURE_QUEUE_SIZE = 200 # was 50 — allow more queuing
CACHE_SIZE = 2000             # was 500 — more caching under load
BATCH_SIZE = 32               # was 10 — larger batches
```

**`lb/load_balancer.py`:**
```python
MAX_CONCURRENT_REQUESTS = 2000  # was 50 — allow 1000 concurrent
MAX_RETRIES = 5                 # was 3 — more retry resilience
```

**Or set via environment variables:**
```bash
# On each worker
MAX_CONCURRENT_TASKS=16 \
BACKPRESSURE_QUEUE_SIZE=200 \
uvicorn workers.worker:app --host 0.0.0.0 --port 8001
```

### 6.2 Minimum Worker Count for 1000 Concurrent

| Per-Worker Slots | Workers Needed | Total Capacity |
|---|---|---|
| 16 concurrent | 16 workers | 256 |
| 16 concurrent | 32 workers | 512 |
| 16 concurrent | 64 workers | 1024 |

**Realistic recommendation:** Deploy **16–20 workers** across **4–5 GPU instances** (4 workers per GPU instance). Each T4 can handle 4 Ollama model copies.

### 6.3 Queue-Based Architecture (Optional but Recommended)

For true 1000-concurrent handling without timeouts, add a Redis-backed job queue:

```bash
# On the LB instance:
sudo apt install redis-server
pip install rq
```

Then on workers, pull from the queue instead of synchronous HTTP:

```python
# New file: workers/queue_worker.py
from rq import Queue
from redis import Redis

redis_conn = Redis(host="10.128.0.10", port=6379)
queue = Queue("llm-inference", connection=redis_conn)

def process_job(query: str, top_k: int):
    docs = retriever.retrieve(query, top_k)
    answer = inference_engine.generate_with_context(query, docs)
    return {"answer": answer, "sources": docs}

# Worker pulls jobs
worker = Worker(queue, connection=redis_conn)
worker.work()
```

Clients submit and poll:
```python
# Client submits request
job = queue.enqueue(process_job, args=(query, top_k))
return {"job_id": job.id}

# Client polls for result
job = Job.fetch(job.id, connection=redis_conn)
if job.is_finished:
    return job.result
```

This decouples client wait time from processing — **1000 concurrent submissions accepted instantly**, processed at GPU speed.

---

## 7. Running Load Tests

### 7.1 From Your Local Machine (Internet Connection)

```bash
cd distributedLLM
source .venv/bin/activate

# 1000 requests, 100 concurrent threads
python client/load_generator.py \
  --url http://34.XXX.YYY.1:8000 \
  --requests 1000 \
  --concurrency 100 \
  --timeout 300 \
  --warmup 10
```

### 7.2 From Inside the Cloud (Lower Latency)

SSH into the LB instance and run the load generator there — avoids internet latency:

```bash
ssh user@34.XXX.YYY.1
cd ~/distributedLLM
source .venv/bin/activate

# Same network — 0.5ms vs 50ms latency
python client/load_generator.py \
  --url http://localhost:8000 \
  --requests 1000 \
  --concurrency 200 \
  --timeout 300 \
  --warmup 10
```

### 7.3 Stress Test (1000 Concurrent at Once)

```bash
python client/stress_test.py \
  --url http://localhost:8000 \
  --concurrent 1000 \
  --timeout 600
```

---

## 8. Monitoring

### 8.1 Real-Time Dashboard

If running the dashboard on the LB instance:
```bash
MASTER_URL=http://10.128.0.10:9000 \
LB_URL=http://10.128.0.10:8000 \
uvicorn dashboard.app:app --host 0.0.0.0 --port 5000
```

Access at `http://34.XXX.YYY.1:5000`

### 8.2 GPU Monitoring Per Node

```bash
# Watch GPU utilization live
watch -n 1 nvidia-smi
```

### 8.3 Key Metrics to Watch

| Metric | Good | Warning | Critical |
|---|---|---|---|
| GPU util | 70-95% | 50-70% | < 50% |
| P50 latency | < 1s | 1-5s | > 5s |
| P95 latency | < 5s | 5-15s | > 15s |
| Error rate | 0% | < 5% | > 5% |
| Queue depth | 0 | 10-50 | > 50 |

---

## 9. Automated Deployment Scripts

### 9.1 Start All Remote Components

```bash
# deploy/start_all.sh
#!/bin/bash
LB_IP="10.128.0.10"

declare -A WORKERS
WORKERS["worker-1"]="10.128.0.11"
WORKERS["worker-2"]="10.128.0.12"
WORKERS["worker-3"]="10.128.0.13"
WORKERS["worker-4"]="10.128.0.14"

# Start master
ssh ubuntu@$LB_IP "cd distributedLLM && source .venv/bin/activate && \
  MASTER_NODE_URL=http://$LB_IP:9000 \
  LOAD_BALANCER_URL=http://$LB_IP:8000 \
  nohup uvicorn master.monitor:app --host 0.0.0.0 --port 9000 > master.log 2>&1 &"

sleep 2

# Start LB
ssh ubuntu@$LB_IP "cd distributedLLM && source .venv/bin/activate && \
  LB_PORT=8000 \
  MASTER_NODE_URL=http://$LB_IP:9000 \
  nohup uvicorn lb.load_balancer:app --host 0.0.0.0 --port 8000 > lb.log 2>&1 &"

sleep 2

# Start workers
for WORKER_ID in "${!WORKERS[@]}"; do
  IP=${WORKERS[$WORKER_ID]}
  ssh ubuntu@$IP "cd distributedLLM && source .venv/bin/activate && \
    WORKER_ID=$WORKER_ID \
    PORT=8001 \
    MASTER_NODE_URL=http://$LB_IP:9000 \
    OLLAMA_URL=http://localhost:11434 \
    MAX_CONCURRENT_TASKS=16 \
    BACKPRESSURE_QUEUE_SIZE=200 \
    nohup uvicorn workers.worker:app --host 0.0.0.0 --port 8001 > worker.log 2>&1 &"
  echo "Started $WORKER_ID on $IP"
done

echo "All components started"
```

### 9.2 Stop Everything

```bash
# deploy/stop_all.sh
for ip in "10.128.0.10" "10.128.0.11" "10.128.0.12" "10.128.0.13" "10.128.0.14"; do
  ssh ubuntu@$ip "pkill -f uvicorn"
  echo "Stopped processes on $ip"
done
```

---

## 10. Cost Estimate (Google Cloud, us-central1)

| Component | Instance Type | GPU | Cost/hr | 1 Week (40h) |
|---|---|---|---|---|
| LB + Master (combined) | n1-standard-2 | None | $0.10 | $4.00 |
| Worker x4 | n1-standard-8 | T4 x1 each | $1.40 | $56.00 |
| **Total** | 5 instances | 4x T4 | **$1.50/hr** | **$60.00** |

Using **Google Cloud $300 credits**: ~200 hours of testing time.

---

## 11. Benchmark Targets

| Configuration | Target Throughput | Est. P50 Latency |
|---|---|---|
| 4 workers (1 GPU each), T4 | 10-20 req/s | 2-5s |
| 8 workers (2 GPU each), T4 | 30-50 req/s | 1-3s |
| 16 workers (4 GPU each), T4 | 80-120 req/s | 0.5-2s |
| 16 workers (4 GPU each), A100 | 200-400 req/s | 0.2-1s |

With **queue-based architecture**, the system can accept 1000 concurrent submissions regardless of backend throughput — users get a `job_id` immediately and poll for results.

---

## 12. Troubleshooting Multi-Node Issues

| Symptom | Cause | Fix |
|---|---|---|
| Workers not registering | Firewall blocking port 9000 | Open TCP 9000 between VPC |
| LB sees 0 workers | Workers can't reach LB | Set `MASTER_NODE_URL` to private IP |
| Query fails with 503 | All workers at capacity | Increase workers or task slots |
| Slow responses from 1 worker | That node's Ollama is busy | Check `nvidia-smi`, restart Ollama |
| ChromaDB returns empty | Embedding model not pulled | `ollama pull nomic-embed-text` |
| High latency but low GPU | Network bottleneck | Move load generator inside cloud VPC |
