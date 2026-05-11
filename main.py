import sys
import subprocess
import os

def main():
    if len(sys.argv) > 1:
        if sys.argv[1] == "worker":
            worker_num = int(sys.argv[2]) if len(sys.argv) > 2 else 1
            port = 8000 + worker_num
            worker_id = f"worker-{worker_num}"
            os.environ["WORKER_ID"] = worker_id
            os.environ["WORKER_PORT"] = str(port)
            print(f"Starting {worker_id} on port {port}")
            subprocess.run(["python", "-m", "uvicorn", "workers.worker:app", "--host", "127.0.0.1", "--port", str(port)])
        elif sys.argv[1] == "master":
            print("Starting Master Node on port 9000")
            subprocess.run(["python", "-m", "uvicorn", "master.monitor:app", "--host", "127.0.0.1", "--port", "9000"])
        elif sys.argv[1] == "lb":
            print("Starting Load Balancer on port 8000")
            subprocess.run(["python", "-m", "uvicorn", "lb.load_balancer:app", "--host", "127.0.0.1", "--port", "8000"])
        elif sys.argv[1] == "dashboard":
            print("Starting Admin Dashboard on port 7000")
            subprocess.run(["python", "-m", "uvicorn", "dashboard.app:app", "--host", "127.0.0.1", "--port", "7000"])
        else:
            print("Usage: python main.py [worker <num>|master|lb|dashboard]")
    else:
        print("Distributed LLM Inference System")
        print("\nTo start individual components:")
        print("  python main.py master      - Start Master Node (port 9000)")
        print("  python main.py worker <n>  - Start Worker n (ports 8001+)")
        print("  python main.py lb          - Start Load Balancer (port 8000)")
        print("  python main.py dashboard   - Start Admin Dashboard (port 7000)")
        print("\nOr start each component manually in separate terminals:")
        print("  python -m uvicorn master.monitor:app --host 127.0.0.1 --port 9000")
        print("  $env:WORKER_ID=\"worker-1\"; $env:WORKER_PORT=\"8001\"; python -m uvicorn workers.worker:app --host 127.0.0.1 --port 8001")
        print("  python -m uvicorn lb.load_balancer:app --host 127.0.0.1 --port 8000")
        print("  python -m uvicorn dashboard.app:app --host 127.0.0.1 --port 7000")

if __name__ == "__main__":
    main()