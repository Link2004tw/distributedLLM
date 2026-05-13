import os, sys, time, signal, subprocess, socket

ROOT = os.path.dirname(os.path.abspath(__file__))
os.chdir(ROOT)

def kill_by_port(port):
    try:
        r = subprocess.run(f"netstat -ano | findstr :{port} ", shell=True, capture_output=True, text=True)
        for line in r.stdout.splitlines():
            parts = line.strip().split()
            if len(parts) >= 5 and "LISTENING" in line:
                pid = int(parts[4])
                if pid != 0:
                    subprocess.run(f"taskkill /f /pid {pid} >nul 2>&1", shell=True)
    except: pass

if "--stop" in sys.argv:
    print("Stopping all services...")
    for p in [8000, 8001, 8002, 8003, 8004, 8005, 8100, 9000]:
        kill_by_port(p)
    print("Done.")
    sys.exit(0)

def start_component(name, module, port, env=None):
    merged = os.environ.copy()
    if env:
        merged.update(env)
    merged["PORT"] = str(port)
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", f"{module}:app",
         "--port", str(port), "--log-level", "warning"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=merged
    )
    print(f"  [{name}] started on port {port} (PID {proc.pid})")
    return proc

def wait_for_port(port, timeout=20):
    start = time.time()
    while time.time() - start < timeout:
        try:
            s = socket.socket()
            s.settimeout(1)
            s.connect(("127.0.0.1", port))
            s.close()
            return True
        except: pass
        time.sleep(0.5)
    return False

print("=== Distributed LLM Quick Setup ===\n")

print("[1/5] Stopping existing processes...")
for p in [8000, 8001, 8002, 8003, 8004, 8005, 8100, 9000]:
    kill_by_port(p)
time.sleep(2)

print("[2/5] Starting Master...")
procs = [start_component("master", "master.monitor", 9000)]
time.sleep(1)

print("[3/5] Starting Workers...")
for i in range(1, 5):
    procs.append(start_component(f"worker-{i}", "workers.worker", 8000 + i,
                                 {"WORKER_ID": f"worker-{i}"}))
    time.sleep(0.5)

print("[4/5] Starting LB and Dashboard...")
procs.append(start_component("lb", "lb.load_balancer", 8000))
procs.append(start_component("dashboard", "dashboard.app", 8100))

print("\nWaiting for services to be ready (this may take 30-60s)...")
ports = {"Master": 9000, "Worker-1": 8001, "Worker-2": 8002,
         "Worker-3": 8003, "Worker-4": 8004, "LB": 8000, "Dashboard": 8100}
lb_ready = False
for name, port in ports.items():
    ok = wait_for_port(port, 40)
    print(f"  [{'OK' if ok else 'FAIL'}] {name} (port {port})")
    if port == 8000 and ok:
        lb_ready = True

if lb_ready:
    print("\n[5/5] Sending 10 test queries...")
    import httpx
    time.sleep(2)
    for i in range(10):
        try:
            r = httpx.post("http://localhost:8000/query",
                          json={"query": f"Tell me something interesting. query-{i}", "top_k": 3},
                          timeout=60)
            print(f"  Query {i}: {'OK' if r.status_code == 200 else 'FAIL'}")
        except Exception as e:
            print(f"  Query {i}: FAIL - {e}")
        time.sleep(0.2)

print(f"\n=== Setup Complete ===")
print(f"  Dashboard: http://localhost:8100")
print(f"  Query:     http://localhost:8000/query")
print(f"  Master:    http://localhost:9000/health")
print(f"\nAll services are running in the background.")
print(f"To stop everything later, run: python quick_setup.py --stop")
