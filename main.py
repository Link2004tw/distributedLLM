import sys
import os
import time
import signal
import subprocess
import platform


IS_WINDOWS = platform.system() == "Windows"


def kill_process(name: str):
    try:
        if IS_WINDOWS:
            subprocess.run(["taskkill", "/f", "/im", name],
                           capture_output=True, timeout=10)
        else:
            subprocess.run(["pkill", "-f", name],
                           capture_output=True, timeout=10)
    except Exception:
        pass


def start_component(name: str, module: str, port: int, env: dict = None):
    merged = os.environ.copy()
    if env:
        merged.update(env)
    merged["PORT"] = str(port)
    if name.startswith("worker"):
        merged["WORKER_ID"] = name
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", f"{module}:app",
         "--port", str(port), "--log-level", "warning"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        env=merged
    )
    print(f"  [{name}] started on port {port} (PID {proc.pid})")
    return proc


def start_all():
    procs = []
    script_dir = os.path.dirname(os.path.abspath(__file__))
    print("Starting Distributed LLM Inference System...\n")

    print("Starting Master Node...")
    procs.append(start_component("master", "master.monitor", 9000))

    for i in range(1, 5):
        procs.append(start_component(f"worker-{i}", "workers.worker", 8000 + i))

    print("Starting NGINX...")
    kill_process("nginx")
    time.sleep(1)
    nginx_available = False
    nginx_cmd = "nginx.exe" if IS_WINDOWS else "nginx"
    nginx_conf = os.path.join(script_dir, "lb", "nginx.conf")
    try:
        subprocess.Popen([nginx_cmd, "-c", nginx_conf],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print("  [nginx] started on port 8000")
        nginx_available = True
    except FileNotFoundError:
        print("  [nginx] not found — starting LB service on port 8000 instead")
        procs.append(start_component("lb", "lb.load_balancer", 8000))

    print("Starting LB Controller...")
    procs.append(start_component("lb-controller", "lb.app", 8005))

    print("\nAll components started. System is ready.")
    print("  Entry point:   http://localhost:8000/query")
    print("  Master:        http://localhost:9000/health")
    print("  Stats:         http://localhost:8000/stats (if LB running on 8000)")
    print("  Press Ctrl+C to stop all components.\n")

    try:
        for p in procs:
            p.wait()
    except KeyboardInterrupt:
        print("\nShutting down all components...")
    finally:
        for p in procs:
            p.terminate()
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                p.kill()
        kill_process("nginx")
        print("All components stopped.")


def stop_all():
    print("Stopping all components...")
    kill_process("uvicorn")
    kill_process("nginx")
    time.sleep(1)
    print("All components stopped.")


def colab():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.chdir(script_dir)

    print("=" * 60)
    print("COLAB DEPLOYMENT")
    print("=" * 60)

    print("\n[1/5] Installing Python dependencies...")
    subprocess.run([sys.executable, "-m", "pip", "install", "-q", "-r", "requirements.txt"],
                   capture_output=True)

    print("[2/5] Ingesting RAG documents...")
    subprocess.run([sys.executable, "ingest.py"], capture_output=True)
    print("  ChromaDB ready")

    print("[3/5] Starting system components...")
    os.environ["SIMULATION"] = "true"

    procs = []
    print("  Starting Master Node...")
    procs.append(start_component("master", "master.monitor", 9000))
    time.sleep(2)

    for i in range(1, 5):
        env = {"MAX_CONCURRENT_TASKS": "8", "BACKPRESSURE_QUEUE_SIZE": "200"}
        procs.append(start_component(f"worker-{i}", "workers.worker", 8000 + i, env))
        time.sleep(1)

    print("  Starting Load Balancer...")
    procs.append(start_component("lb", "lb.load_balancer", 8000))

    print("\n[4/5] Waiting for services to initialize...")
    time.sleep(8)

    import httpx
    for name, url in [("Master", "http://localhost:9000/health"),
                       ("Worker-1", "http://localhost:8001/health"),
                       ("Worker-2", "http://localhost:8002/health"),
                       ("Worker-3", "http://localhost:8003/health"),
                       ("Worker-4", "http://localhost:8004/health"),
                       ("LB", "http://localhost:8000/health")]:
        try:
            r = httpx.get(url, timeout=5)
            print(f"  [OK] {name}")
        except Exception:
            print(f"  [FAIL] {name}")

    workers_r = httpx.get("http://localhost:9000/workers", timeout=5)
    registered = len(workers_r.json()["workers"])
    print(f"\n  Workers registered: {registered}")

    print("\n[5/5] Running quick benchmark...")
    try:
        result = subprocess.run(
            [sys.executable, "client/load_generator.py",
             "--url", "http://localhost:8000",
             "--requests", "50", "--concurrency", "10"],
            capture_output=True, text=True, timeout=300
        )
        print(result.stdout)
    except Exception as e:
        print(f"  Benchmark error: {e}")

    print("\n" + "=" * 60)
    print("COLAB DEPLOYMENT COMPLETE")
    print("=" * 60)
    print("  Query endpoint:  http://localhost:8000/query")
    print("  Stats:           http://localhost:8000/stats")
    print("  Workers:         http://localhost:9000/workers")
    print("  Press Ctrl+C to stop.\n")

    try:
        for p in procs:
            p.wait()
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        for p in procs:
            p.terminate()
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                p.kill()
        print("All components stopped.")


def main():
    if len(sys.argv) < 2:
        print("Distributed LLM Inference System")
        print()
        print("Usage:")
        print("  python main.py start              Start all components")
        print("  python main.py stop               Stop all components")
        print("  python main.py colab              Full Colab setup + benchmark")
        print("  python main.py master             Start Master Node only")
        print("  python main.py worker <n>         Start Worker n (1-4)")
        print("  python main.py lb                 Start NGINX")
        print("  python main.py controller         Start LB Controller")
        return

    cmd = sys.argv[1]

    if cmd == "start":
        start_all()
    elif cmd == "stop":
        stop_all()
    elif cmd == "colab":
        colab()
    elif cmd == "master":
        print("Starting Master Node on port 9000")
        subprocess.run(["uvicorn", "master.monitor:app", "--port", "9000"])
    elif cmd == "worker":
        worker_num = int(sys.argv[2]) if len(sys.argv) > 2 else 1
        port = 8000 + worker_num
        os.environ["WORKER_ID"] = f"worker-{worker_num}"
        os.environ["PORT"] = str(port)
        print(f"Starting worker-{worker_num} on port {port}")
        subprocess.run(["uvicorn", "workers.worker:app", "--port", str(port)])
    elif cmd == "lb":
        kill_process("nginx")
        time.sleep(1)
        script_dir = os.path.dirname(os.path.abspath(__file__))
        nginx_cmd = "nginx.exe" if IS_WINDOWS else "nginx"
        nginx_conf = os.path.join(script_dir, "lb", "nginx.conf")
        try:
            subprocess.Popen([nginx_cmd, "-c", nginx_conf],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            print("NGINX started on port 8000")
        except FileNotFoundError:
            print("NGINX not found. Install it or use: uvicorn lb.load_balancer:app --port 8000")
    elif cmd == "controller":
        print("Starting LB Controller on port 8005")
        subprocess.run(["uvicorn", "lb.app:app", "--port", "8005"])
    else:
        print(f"Unknown command: {cmd}")
        print("Usage: python main.py [start|stop|colab|master|worker|lb|controller]")


if __name__ == "__main__":
    main()
