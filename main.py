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
            os.environ["PORT"] = str(port)
            print(f"Starting {worker_id} on port {port}")
            subprocess.run(["uvicorn", "workers.worker:app", "--port", str(port)])
        elif sys.argv[1] == "master":
            print("Starting Master Node on port 9000")
            subprocess.run(["uvicorn", "master.monitor:app", "--port", "9000"])
        elif sys.argv[1] == "lb":
            nginx_exe = os.path.join(os.path.dirname(__file__), "lb", "nginx", "nginx.exe")
            nginx_dir = os.path.join(os.path.dirname(__file__), "lb", "nginx")
            if os.path.exists(nginx_exe):
                print("Starting NGINX Load Balancer on port 8000")
                subprocess.Popen(
                    [nginx_exe, "-p", nginx_dir],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
                )
            else:
                print("NGINX not found at", nginx_exe)
                print("Run setup.ps1 first or use 'controller' for Python LB fallback")
        elif sys.argv[1] == "controller":
            print("Starting LB Controller on port 8005")
            subprocess.run(["uvicorn", "lb.app:app", "--port", "8005"])
        elif sys.argv[1] == "dashboard":
            print("Starting Admin Dashboard on port 5000")
            subprocess.run(["uvicorn", "dashboard.app:app", "--port", "5000"])
        else:
            print("Usage: python main.py [worker <num>|master|lb|controller|dashboard]")
    else:
        print("Distributed LLM Inference System")
        print("\nTo start individual components:")
        print("  python main.py master       - Start Master Node (port 9000)")
        print("  python main.py worker <n>   - Start Worker n (ports 8001+)")
        print("  python main.py lb           - Start NGINX Load Balancer (port 8000)")
        print("  python main.py controller   - Start LB Controller (port 8005)")
        print("  python main.py dashboard    - Start Admin Dashboard (port 5000)")
        print("\nOr start each component manually:")
        print("  uvicorn master.monitor:app --port 9000")
        print("  uvicorn workers.worker:app --port 8001")
        print("  uvicorn workers.worker:app --port 8002")
        print("  uvicorn workers.worker:app --port 8003")
        print("  uvicorn workers.worker:app --port 8004")
        print("  .\\lb\\nginx\\nginx.exe -p lb\\nginx")
        print("  uvicorn lb.app:app --port 8005")
        print("  uvicorn dashboard.app:app --port 5000")


if __name__ == "__main__":
    main()
