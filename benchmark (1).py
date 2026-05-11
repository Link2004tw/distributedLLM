import os
import sys
import time
import json
import argparse
import subprocess
import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def log(msg):
    print(f"[benchmark] {msg}")


def check_ollama(target_model: str = ""):
    try:
        r = subprocess.run(["ollama", "list"], capture_output=True, text=True, timeout=10)
        if r.returncode != 0:
            log("ERROR: Ollama not running. Start it with 'ollama serve'")
            return False
        output = r.stdout.lower()
        required = {"nomic-embed-text", target_model.lower()} if target_model else {"nomic-embed-text"}
        required.discard("")
        missing = [m for m in required if m not in output]
        for m in missing:
            log(f"ERROR: Model '{m}' not pulled. Run: ollama pull {m}")
        if missing:
            return False
        return True
    except FileNotFoundError:
        log("ERROR: ollama not found in PATH")
        return False
    except subprocess.TimeoutExpired:
        log("ERROR: ollama list timed out")
        return False


def setup_nginx():
    nginx_exe = ROOT / "lb" / "nginx" / "nginx.exe"
    if nginx_exe.exists():
        log("NGINX already installed")
        return True
    log("Setting up NGINX...")
    r = subprocess.run(
        ["powershell", "-File", str(ROOT / "lb" / "setup.ps1")],
        capture_output=True, text=True, timeout=60
    )
    if r.returncode != 0:
        log(f"NGINX setup failed:\n{r.stderr}")
        return False
    log("NGINX setup complete")
    return True


def start_nginx():
    nginx_exe = ROOT / "lb" / "nginx" / "nginx.exe"
    nginx_dir = ROOT / "lb" / "nginx"
    conf_src = ROOT / "lb" / "nginx.conf"
    conf_dst = nginx_dir / "conf" / "nginx.conf"

    if not nginx_exe.exists():
        log("NGINX not found, run setup first")
        return False

    conf_dst.parent.mkdir(parents=True, exist_ok=True)
    import shutil
    shutil.copy2(str(conf_src), str(conf_dst))

    subprocess.run(["taskkill", "/f", "/im", "nginx.exe"],
                   capture_output=True, timeout=5)
    time.sleep(1)
    p = subprocess.Popen(
        [str(nginx_exe), "-p", str(nginx_dir)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL
    )
    time.sleep(2)
    log("NGINX started on port 8000")
    return True


def stop_nginx():
    subprocess.run(["taskkill", "/f", "/im", "nginx.exe"],
                   capture_output=True, timeout=5)
    log("NGINX stopped")


def start_component(name: str, module: str, port: int, env: dict = None):
    merged = os.environ.copy()
    if env:
        merged.update(env)
    merged["PORT"] = str(port)
    if name.startswith("worker"):
        merged["WORKER_ID"] = name

    p = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", f"{module}:app",
         "--port", str(port), "--log-level", "warning"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        env=merged
    )
    return p


def wait_for_ready(url: str, timeout: int = 15):
    import httpx
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = httpx.get(url, timeout=3)
            if r.status_code == 200:
                return True
        except Exception:
            pass
        time.sleep(1)
    return False


def wait_for_worker_ready(url: str, timeout: int = 90):
    import httpx
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            r = httpx.get(f"{url}/ready", timeout=10)
            data = r.json()
            if data.get("ready"):
                return True
            log(f"  Worker not ready: {data.get('error', 'unknown')}")
        except Exception:
            pass
        time.sleep(3)
    return False


def run_load_test(total_requests: int, concurrency: int, url: str = "http://127.0.0.1:8000", timeout_s: float = 120.0, worker_urls: list = None):
    import httpx
    from concurrent.futures import ThreadPoolExecutor, as_completed
    import itertools

    if worker_urls:
        worker_iter = itertools.cycle([f"{w}/query" for w in worker_urls])
        def get_url(i):
            return next(worker_iter)
    else:
        single_url = f"{url}/query"
        def get_url(i):
            return single_url

    samples = [
        "What is distributed inference?",
        "Explain load balancing.",
        "What is RAG?",
        "How does fault tolerance work?",
        "What is the role of the master node?",
        "Explain round robin routing.",
        "Explain least connections routing.",
        "What happens if one worker fails?",
        "How can throughput be improved?",
        "Summarize the system architecture."
    ]

    results = []
    test_start = time.perf_counter()

    with httpx.Client(limits=httpx.Limits(max_connections=concurrency,
                                          max_keepalive_connections=concurrency)) as client:
        with ThreadPoolExecutor(max_workers=concurrency) as executor:
            def send(i):
                payload = {"query": samples[i % len(samples)], "top_k": 1}
                start = time.perf_counter()
                try:
                    r = client.post(get_url(i), json=payload, timeout=timeout_s)
                    lat = time.perf_counter() - start
                    return {"success": r.status_code == 200, "latency": lat,
                            "status": r.status_code, "error": None if r.status_code == 200 else r.text}
                except Exception as e:
                    lat = time.perf_counter() - start
                    return {"success": False, "latency": lat, "status": None, "error": str(e)}
            futures = [executor.submit(send, i) for i in range(total_requests)]
            for f in as_completed(futures):
                results.append(f.result())

    total_time = time.perf_counter() - test_start
    successful = [r for r in results if r["success"]]
    failed = [r for r in results if not r["success"]]
    latencies = [r["latency"] for r in successful]
    throughput = total_requests / total_time if total_time > 0 else 0

    def pct(vals, p):
        if not vals:
            return 0
        s = sorted(vals)
        idx = max(0, min(int((p / 100) * len(s)) - 1, len(s) - 1))
        return s[idx]

    return {
        "total": total_requests,
        "success": len(successful),
        "failed": len(failed),
        "error_rate": (len(failed) / total_requests) * 100 if total_requests else 0,
        "total_time_s": round(total_time, 2),
        "throughput_rps": round(throughput, 2),
        "avg_latency_s": round(sum(latencies) / len(latencies), 4) if latencies else 0,
        "min_latency_s": round(min(latencies), 4) if latencies else 0,
        "max_latency_s": round(max(latencies), 4) if latencies else 0,
        "p50_s": round(pct(latencies, 50), 4) if latencies else 0,
        "p95_s": round(pct(latencies, 95), 4) if latencies else 0,
        "p99_s": round(pct(latencies, 99), 4) if latencies else 0,
        "sample_errors": [r["error"] for r in failed[:5] if r["error"]],
    }


def run_single_benchmark(label: str, workers: int, model: str,
                         requests: int, concurrency: int,
                         nginx_strategy: str = "round_robin",
                         ollama_num_gpu: str = "",
                         ollama_ctx: str = "",
                         ollama_batch: str = "",
                         embedding_model: str = "nomic-embed-text:latest",
                         direct: bool = False):
    log(f"\n{'='*60}")
    log(f"BENCHMARK: {label}")
    log(f"  workers={workers}, model={model}, concurrency={concurrency}")
    log(f"  strategy={'direct' if direct else nginx_strategy}, num_gpu={ollama_num_gpu or 'default'}")
    log(f"{'='*60}")

    procs = []
    try:
        if not direct:
            nginx_exe = ROOT / "lb" / "nginx" / "nginx.exe"
            nginx_dir = ROOT / "lb" / "nginx"
            nginx_conf_path = ROOT / "lb" / "nginx" / "conf" / "nginx.conf"
            if nginx_conf_path.exists():
                content = nginx_conf_path.read_text()
                if nginx_strategy == "least_connections":
                    content = content.replace("# least_conn;", "least_conn;")
                    if "least_conn;" not in content:
                        content = content.replace("server localhost", "least_conn;\n        server localhost")
                else:
                    content = content.replace("least_conn;", "# least_conn;")
                nginx_conf_path.write_text(content)
                subprocess.run([str(nginx_exe), "-p", str(nginx_dir), "-s", "reload"],
                               capture_output=True, timeout=10)
            log(f"NGINX strategy: {nginx_strategy}")

        log("Starting master...")
        p = start_component("master", "master.monitor", 9000)
        procs.append(p)
        if not wait_for_ready("http://127.0.0.1:9000/health"):
            log("FAIL: master did not start")
            return None

        for i in range(1, workers + 1):
            port = 8000 + i
            wid = f"worker-{i}"
            log(f"Starting {wid} on port {port}...")
            env = {
                "LLM_MODEL": model,
                "EMBEDDING_MODEL": embedding_model,
                "WORKER_ID": wid,
            }
            if ollama_num_gpu:
                env["OLLAMA_NUM_GPU"] = ollama_num_gpu
            if ollama_ctx:
                env["OLLAMA_CONTEXT_LENGTH"] = ollama_ctx
            if ollama_batch:
                env["OLLAMA_BATCH_SIZE"] = ollama_batch
            p = start_component(wid, "workers.worker", port, env=env)
            procs.append(p)
            if not wait_for_worker_ready(f"http://127.0.0.1:{port}"):
                log(f"FAIL: {wid} not ready (model load error)")
                return None

        log("Warming up models (cold-start avoidance)...")
        import httpx
        warmup_targets = [f"http://127.0.0.1:{8000 + i}" for i in range(1, workers + 1)] if direct else ["http://127.0.0.1:8000"]
        for target in warmup_targets:
            for _ in range(2):
                try:
                    httpx.post(f"{target}/query",
                               json={"query": "warmup", "top_k": 1},
                               timeout=30.0)
                except Exception:
                    pass

        log("Running load test...")
        worker_urls = [f"http://127.0.0.1:{8000 + i}" for i in range(1, workers + 1)] if direct else None
        result = run_load_test(requests, concurrency, worker_urls=worker_urls)

        result["label"] = label
        result["config"] = {
            "workers": workers,
            "model": model,
            "concurrency": concurrency,
            "strategy": "direct" if direct else nginx_strategy,
            "ollama_num_gpu": ollama_num_gpu,
            "ollama_ctx": ollama_ctx,
            "ollama_batch": ollama_batch,
            "embedding_model": embedding_model,
        }
        return result

    finally:
        log("Cleaning up...")
        for p in procs:
            p.terminate()
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                p.kill()
        time.sleep(1)


def run_benchmark_suite(args):
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    results = []

    if args.model:
        models = [args.model]
    else:
        models = ["smollm2:135m", "smollm2:360m"]

    available = []
    for m in models:
        if check_ollama(m):
            available.append(m)
        else:
            log(f"SKIPPING model '{m}' — not pulled. Run: ollama pull {m}")
    if not available:
        log("No models available. Exiting.")
        return
    models = available

    if args.workers:
        worker_counts = [args.workers]
    else:
        worker_counts = [1, 2, 4]

    if args.concurrency:
        concurrencies = [args.concurrency]
    else:
        concurrencies = [10, 50]

    requests_per_test = args.requests

    for model in models:
        for wc in worker_counts:
            for cc in concurrencies:
                label = f"model={model} workers={wc} concurrency={cc}"
                if not args.direct:
                    label += " rr"
                r = run_single_benchmark(
                    label=label,
                    workers=wc,
                    model=model,
                    requests=requests_per_test,
                    concurrency=cc,
                    nginx_strategy="round_robin",
                    ollama_num_gpu=args.num_gpu,
                    ollama_ctx=args.ctx,
                    ollama_batch=args.batch,
                    embedding_model=args.embedding_model,
                    direct=args.direct,
                )
                if r:
                    results.append(r)
                    _print_result(r)

                if not args.direct:
                    label_lc = f"model={model} workers={wc} concurrency={cc} lc"
                    r = run_single_benchmark(
                        label=label_lc,
                        workers=wc,
                        model=model,
                        requests=requests_per_test,
                        concurrency=cc,
                        nginx_strategy="least_connections",
                        ollama_num_gpu=args.num_gpu,
                        ollama_ctx=args.ctx,
                        ollama_batch=args.batch,
                        embedding_model=args.embedding_model,
                        direct=args.direct,
                    )
                if r:
                    results.append(r)
                    _print_result(r)

    out_path = ROOT / f"benchmark_results_{timestamp}.json"
    out_path.write_text(json.dumps(results, indent=2))
    log(f"\nAll results saved to: {out_path}")

    _print_summary(results)
    return results


def _print_result(r):
    print(f"\n--- {r['label']} ---")
    print(f"  Success: {r['success']}/{r['total']}  |  Error rate: {r['error_rate']:.1f}%")
    print(f"  Throughput: {r['throughput_rps']} req/s  |  Total time: {r['total_time_s']}s")
    if r['avg_latency_s']:
        print(f"  Latency: avg={r['avg_latency_s']:.4f}s  p50={r['p50_s']:.4f}s  p95={r['p95_s']:.4f}s  p99={r['p99_s']:.4f}s")
    errors = r.get("sample_errors", [])
    if errors:
        print(f"  Sample errors:")
        for e in errors[:3]:
            print(f"    - {e[:120]}")


def _print_summary(results):
    print(f"\n{'='*60}")
    print("BENCHMARK SUMMARY")
    print(f"{'='*60}")
    print(f"{'Label':<50} {'Throughput':>10} {'Avg Lat':>10} {'P95':>10} {'Err%':>8}")
    print("-" * 88)
    for r in results:
        label = r.get("label", "")[:50]
        thr = f"{r['throughput_rps']}r/s"
        avg = f"{r['avg_latency_s']:.3f}s" if r['avg_latency_s'] else "-"
        p95 = f"{r['p95_s']:.3f}s" if r['p95_s'] else "-"
        err = f"{r['error_rate']:.1f}%"
        print(f"{label:<50} {thr:>10} {avg:>10} {p95:>10} {err:>8}")


def main():
    parser = argparse.ArgumentParser(description="Distributed LLM Benchmark Suite")
    parser.add_argument("--requests", type=int, default=100,
                        help="Requests per test (default: 100)")
    parser.add_argument("--model", type=str, default="",
                        help="Specific model to test (default: all)")
    parser.add_argument("--workers", type=int, default=0,
                        help="Specific worker count (default: 1,2,4)")
    parser.add_argument("--concurrency", type=int, default=0,
                        help="Specific concurrency (default: 10,50)")
    parser.add_argument("--num-gpu", type=str, default="",
                        help="OLLAMA_NUM_GPU layers (default: all)")
    parser.add_argument("--ctx", type=str, default="",
                        help="OLLAMA_CONTEXT_LENGTH (default: 2048)")
    parser.add_argument("--batch", type=str, default="",
                        help="OLLAMA_BATCH_SIZE (default: 512)")
    parser.add_argument("--embedding-model", type=str, default="nomic-embed-text:latest",
                        help="Embedding model (default: nomic-embed-text:latest)")
    parser.add_argument("--single", action="store_true",
                        help="Run a single quick test and exit")
    parser.add_argument("--direct", action="store_true",
                        help="Bypass NGINX, send requests directly to workers")
    args = parser.parse_args()

    target = args.model or "smollm2:135m"
    if not check_ollama(target):
        sys.exit(1)

    if not args.direct:
        if not setup_nginx():
            sys.exit(1)
        if not start_nginx():
            sys.exit(1)

    try:
        if args.single:
            r = run_single_benchmark(
                label="single-test",
                workers=args.workers or 2,
                model=args.model or "smollm2:135m",
                requests=args.requests,
                concurrency=args.concurrency or 10,
                ollama_num_gpu=args.num_gpu,
                ollama_ctx=args.ctx,
                ollama_batch=args.batch,
                embedding_model=args.embedding_model,
                direct=args.direct,
            )
            if r:
                _print_result(r)
                out = ROOT / "benchmark_result_latest.json"
                out.write_text(json.dumps(r, indent=2))
                log(f"Result saved to {out}")
        else:
            run_benchmark_suite(args)
    finally:
        if not args.direct:
            stop_nginx()


if __name__ == "__main__":
    main()
