import os
import sys
import time
import subprocess

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
os.environ["CUDA_VISIBLE_DEVICES"] = "0"

import httpx

LB_URL = "http://127.0.0.1:8000"
MASTER_URL = "http://127.0.0.1:9000"


def kill_port(port: int) -> bool:
    result = subprocess.run(
        f'netstat -ano | findstr :{port}',
        shell=True, capture_output=True, text=True
    )
    for line in result.stdout.strip().split("\n"):
        if line:
            parts = line.split()
            for part in parts:
                if part.isdigit() and int(part) > 100:
                    try:
                        r = subprocess.run(
                            f'taskkill /F /PID {part}',
                            shell=True, capture_output=True
                        )
                        print(f"  Killed PID {part} on port {port}")
                        return True
                    except Exception:
                        pass
    return False


def start_worker(port: int, worker_id: str) -> subprocess.Popen:
    env = os.environ.copy()
    env["WORKER_ID"] = worker_id
    env["PORT"] = str(port)
    env["OLLAMA_URL"] = "http://localhost:11434"
    env["MASTER_NODE_URL"] = MASTER_URL

    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "workers.worker:app",
         "--port", str(port), "--host", "127.0.0.1"],
        env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    print(f"  Started {worker_id} on port {port}, PID={proc.pid}")
    return proc


def get_lb_workers():
    r = httpx.get(f"{LB_URL}/workers", timeout=5)
    return r.json()["workers"]


def get_master_workers():
    r = httpx.get(f"{MASTER_URL}/workers", timeout=5)
    return r.json()["workers"]


def send_requests(count: int, timeout: float = 45.0) -> tuple:
    successes = 0
    failures = 0
    for i in range(count):
        client = httpx.Client(timeout=timeout)
        try:
            r = client.post(
                f"{LB_URL}/query",
                json={"query": f"test {i}", "top_k": 1}
            )
            if r.status_code == 200:
                successes += 1
            else:
                failures += 1
        except Exception:
            failures += 1
        finally:
            client.close()
    return successes, failures


def test_master_failure_detection():
    print("\n" + "=" * 60)
    print("TEST: Master Failure Detection")
    print("=" * 60)

    workers_before = get_master_workers()
    print(f"  Master has {len(workers_before)} workers: "
          f"{[w['worker_id'] for w in workers_before]}")

    killed = kill_port(8001)
    if not killed:
        print("  SKIP: Could not kill worker on port 8001")
        return False

    print(f"  Worker killed. Waiting 8 seconds for Master heartbeat (interval=5s)...")
    time.sleep(8)

    workers_after = get_master_workers()
    worker_8001 = next(
        (w for w in workers_after if w.get("port") == 8001), None
    )

    if worker_8001:
        healthy = worker_8001.get("healthy", True)
        last_hb = time.time() - worker_8001.get("last_heartbeat", 0)
        print(f"  Worker 8001: healthy={healthy}, "
              f"last_heartbeat={last_hb:.1f}s ago, "
              f"connections={worker_8001.get('active_connections', 0)}")

        if not healthy:
            print("  [PASS] Master correctly detected worker failure")
            return True
        else:
            print("  [WARN] Worker not marked unhealthy by Master yet")
            return False
    else:
        print("  [INFO] Worker 8001 not in Master registry")
        return False


def test_lb_serves_remaining_workers():
    print("\n" + "=" * 60)
    print("TEST: LB Routes to Remaining Workers")
    print("=" * 60)

    workers = get_lb_workers()
    healthy = [w for w in workers if w.get("healthy", False)]
    print(f"  {len(healthy)} healthy workers: {[w['worker_id'] for w in healthy]}")

    if len(healthy) < 2:
        print("  SKIP: Need at least 2 healthy workers")
        return None

    killed = kill_port(healthy[0]["port"])
    if not killed:
        print(f"  SKIP: Could not kill worker on port {healthy[0]['port']}")
        return None

    time.sleep(3)
    print("  Worker killed. Sending requests through remaining workers...")

    successes, failures = send_requests(15, timeout=30.0)
    rate = successes / 15 * 100

    print(f"  {successes}/15 succeeded ({rate:.0f}%), {failures}/15 failed")

    if successes >= 10:
        print(f"  [PASS] LB successfully routed to remaining workers")
        return True
    elif successes >= 5:
        print(f"  [WARN] Degraded but partially functional")
        return False
    else:
        print(f"  [FAIL] Too many failures: {failures}/15")
        return False


def test_worker_restart_recovery():
    print("\n" + "=" * 60)
    print("TEST: Worker Restart and Recovery")
    print("=" * 60)

    port = 8002
    worker_id = f"recovery-test-{port}"

    print(f"  Killing worker on port {port}...")
    kill_port(port)
    time.sleep(2)

    print("  Sending requests during failure...")
    successes_during, failures_during = send_requests(10, timeout=30.0)
    print(f"  During failure: {successes_during}/10 succeeded")

    print(f"  Restarting worker on port {port}...")
    proc = start_worker(port, worker_id)
    time.sleep(6)

    workers = get_lb_workers()
    restarted = next((w for w in workers if w.get("port") == port), None)

    if restarted:
        print(f"  Worker {port} in LB: healthy={restarted.get('healthy', False)}")

    print("  Sending requests after restart...")
    successes_after, _ = send_requests(10, timeout=60.0)
    print(f"  After recovery: {successes_after}/10 succeeded")

    if successes_after >= 8:
        print(f"  [PASS] System recovered successfully")
        return True
    elif successes_after >= 5:
        print(f"  [WARN] Partial recovery")
        return False
    else:
        print(f"  [FAIL] Recovery failed")
        return False


def test_multi_worker_failure():
    print("\n" + "=" * 60)
    print("TEST: Multiple Worker Failure")
    print("=" * 60)

    killed_ports = []
    for port in [8003, 8004]:
        if kill_port(port):
            killed_ports.append(port)
            print(f"  Killed port {port}")

    if len(killed_ports) < 2:
        print("  SKIP: Could not kill enough workers")
        return False

    time.sleep(3)

    workers = get_lb_workers()
    remaining_healthy = [w for w in workers if w.get("healthy", False)]
    print(f"  {len(remaining_healthy)} workers remaining healthy")

    successes, failures = send_requests(25, timeout=45.0)
    rate = successes / 25 * 100

    print(f"  {successes}/25 succeeded ({rate:.0f}%), {failures}/25 failed")

    restarted = 0
    for port in killed_ports:
        p = start_worker(port, f"worker-{port}")
        restarted += 1
        time.sleep(1)

    time.sleep(5)

    workers_after = get_lb_workers()
    healthy_after = [w for w in workers_after if w.get("healthy", False)]
    print(f"  After restart: {len(healthy_after)} workers healthy")

    if successes >= 20:
        print(f"  [PASS] System handled multi-worker failure")
        return True
    elif successes >= 15:
        print(f"  [WARN] Degraded but functional")
        return False
    else:
        print(f"  [FAIL] System collapsed: {failures}/25 failed")
        return False


def test_baseline_health():
    print("\n" + "=" * 60)
    print("TEST: Baseline System Health")
    print("=" * 60)

    lb_workers = get_lb_workers()
    master_workers = get_master_workers()

    print(f"  LB: {len(lb_workers)} workers, "
          f"healthy: {len([w for w in lb_workers if w.get('healthy')])}")
    print(f"  Master: {len(master_workers)} workers registered")

    for w in lb_workers[:4]:
        print(f"  - {w['worker_id']}: port={w['port']}, "
              f"healthy={w.get('healthy', False)}, "
              f"connections={w.get('active_connections', 0)}, "
              f"latency={w.get('avg_latency_ms', 0):.0f}ms")

    successes, failures = send_requests(10, timeout=60.0)
    print(f"  10 baseline requests: {successes}/10 succeeded")

    if successes >= 8:
        print(f"  [PASS] System baseline healthy")
        return True
    else:
        print(f"  [FAIL] System not healthy: {failures}/10 failed")
        return False


def run_all():
    print("\n" + "=" * 60)
    print("FAILURE SIMULATION TEST SUITE")
    print("=" * 60)

    results = {}

    results["baseline"] = test_baseline_health()
    results["master_detection"] = test_master_failure_detection()
    results["lb_routing"] = test_lb_serves_remaining_workers()
    results["worker_recovery"] = test_worker_restart_recovery()
    results["multi_worker"] = test_multi_worker_failure()

    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    for name, result in results.items():
        status = "PASS" if result else ("WARN" if result is False else "SKIP")
        print(f"  {name:20s}: [{status}]")
    print("=" * 60)


if __name__ == "__main__":
    run_all()