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


def main():
    if len(sys.argv) < 2:
        print("Distributed LLM Inference System")
        print()
        print("Usage:")
        print("  python main.py start              Start all components")
        print("  python main.py stop               Stop all components")
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
        print("Usage: python main.py [start|stop|master|worker|lb|controller]")


if __name__ == "__main__":
    main()
