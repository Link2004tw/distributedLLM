import sys
import subprocess
import os


def main():
    components = [
        ("Master Node", "master.monitor", "9000"),
        ("Worker 1", "workers.worker", "8001"),
        ("Worker 2", "workers.worker", "8002"),
        ("Worker 3", "workers.worker", "8003"),
        ("Worker 4", "workers.worker", "8004"),
        ("Load Balancer", "lb.load_balancer", "8000"),
    ]

    if len(sys.argv) > 1:
        if sys.argv[1] == "worker":
            worker_num = int(sys.argv[2]) if len(sys.argv) > 2 else 1
            port = 8000 + worker_num
            worker_id = f"worker-{worker_num}"
            os.environ["WORKER_ID"] = worker_id
            os.environ["PORT"] = str(port)
            print(f"Starting {worker_id} on port {port}")
            subprocess.run(["uvicorn", "workers.worker:app", "--port", str(port)])
        elif sys.argv[1] == "master":
            print("Starting Master Node on port 9000")
            subprocess.run(["uvicorn", "master.monitor:app", "--port", "9000"])
        elif sys.argv[1] == "lb":
            print("Starting Load Balancer on port 8000")
            subprocess.run(["uvicorn", "lb.load_balancer:app", "--port", "8000"])
        else:
            print("Usage: python main.py [worker <num>|master|lb]")
    else:
        print("Distributed LLM Inference System")
        print("\nTo start individual components:")
        print("  python main.py master      - Start Master Node (port 9000)")
        print("  python main.py worker <n>  - Start Worker n (ports 8001+)")
        print("  python main.py lb          - Start Load Balancer (port 8000)")
        print("\nOr start each component manually in separate terminals:")
        print("  uvicorn master.monitor:app --port 9000")
        print("  uvicorn workers.worker:app --port 8001")
        print("  uvicorn workers.worker:app --port 8002")
        print("  uvicorn workers.worker:app --port 8003")
        print("  uvicorn workers.worker:app --port 8004")
        print("  uvicorn lb.load_balancer:app --port 8000")


if __name__ == "__main__":
    main()