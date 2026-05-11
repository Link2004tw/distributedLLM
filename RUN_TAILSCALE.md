# Tailscale Distributed Deployment

Three machines connected via Tailscale.

## Topology

| Machine  | Tailscale IP       | Runs                                                  |
|----------|--------------------|-------------------------------------------------------|
| PAVLY    | `100.103.28.116`   | Load Balancer (`:8000`) + Master (`:9000`)            |
| ANDREA   | `100.66.241.32`    | Worker 1 (`:8001`) + Worker 2 (`:8002`)               |
| FADY     | `100.124.230.6`    | Worker 3 (`:8003`) + Worker 4 (`:8004`)               |

## Request flow

```
Client → http://100.103.28.116:8000/query
  → Load Balancer forwards to Master
    → Master round-robins to a worker
      → Worker returns answer
```

## Prerequisites (all machines)

```bash
git clone <repo> && cd distributedLLM
python -m venv .venv
source .venv/bin/activate    # Linux/Mac
# or
.venv\Scripts\Activate.ps1   # Windows

pip install -r requirements.txt
```

No Ollama, ChromaDB, or LangChain required — the RAG/LLM modules are simulated.

## Start services

### On ANDREA (two terminals)

```bash
cd distributedLLM
.venv\Scripts\Activate.ps1

# Terminal 1
uvicorn workers.worker:app --host 0.0.0.0 --port 8001

# Terminal 2
uvicorn workers.worker:app --host 0.0.0.0 --port 8002
```

### On FADY (two terminals)

```bash
cd distributedLLM
.venv\Scripts\Activate.ps1

# Terminal 1
uvicorn workers.worker:app --host 0.0.0.0 --port 8003

# Terminal 2
uvicorn workers.worker:app --host 0.0.0.0 --port 8004
```

### On PAVLY (two terminals)

```bash
cd distributedLLM
.venv\Scripts\Activate.ps1

# Terminal 1 — Master
$env:WORKER_URLS="http://100.66.241.32:8001/query,http://100.66.241.32:8002/query,http://100.124.230.6:8003/query,http://100.124.230.6:8004/query"
uvicorn master.monitor:app --host 0.0.0.0 --port 9000

# Terminal 2 — Load Balancer
$env:MASTER_URL="http://100.103.28.116:9000/query"
uvicorn lb.load_balancer:app --host 0.0.0.0 --port 8000
```

Alternatively, create `.env` on PAVLY with the above vars and omit `$env:` prefixes.

## Verify everything is running

Run these from any machine on the Tailscale network:

```bash
# Workers
curl http://100.66.241.32:8001/health
curl http://100.66.241.32:8002/health
curl http://100.124.230.6:8003/health
curl http://100.124.230.6:8004/health

# Master
curl http://100.103.28.116:9000/health
curl http://100.103.28.116:9000/workers

# Load Balancer
curl http://100.103.28.116:8000/health
curl http://100.103.28.116:8000/master
```

Expected responses:

```
# Worker health
{"status":"ok","role":"worker","worker_id":"worker-...","healthy":true,...}

# Master health
{"status":"ok","role":"master","workers_count":4}

# Master workers
{"workers":["http://100.66.241.32:8001/query","http://100.66.241.32:8002/query","http://100.124.230.6:8003/query","http://100.124.230.6:8004/query"],"count":4}

# LB health
{"status":"ok","role":"load_balancer","master_url":"http://100.103.28.116:9000/query"}

# LB master
{"master_url":"http://100.103.28.116:9000/query"}
```

## Smoke test

```bash
curl -X POST http://100.103.28.116:8000/query \
  -H "Content-Type: application/json" \
  -d '{"query":"What is distributed computing?","top_k":1}'
```

Expected: JSON with `answer`, `sources`, `latency_ms`.

## Benchmark

From PAVLY (or any machine):

```bash
cd distributedLLM
python benchmark_1000.py
```

Sends 1000 concurrent requests to `http://100.103.28.116:8000/query` and prints throughput stats.

## Troubleshooting

| Symptom | Likely cause | Fix |
|---------|-------------|-----|
| Connection refused on worker | Worker not started | Check terminal, start uvicorn |
| Master returns 503 | All workers down or WORKER_URLS wrong | Verify workers are running and reachable |
| LB returns 503 | Master down | Check master terminal |
| Tailscale IP unreachable | Tailscale not connected | `tailscale status` on each machine |
| ModuleNotFoundError | Wrong directory | Run from `distributedLLM/` root or set `PYTHONPATH` |
