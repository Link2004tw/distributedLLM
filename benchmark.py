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


def run_load_test(total_requests: int, concurrency: int, url: str = "http://127.0.0.1:8000", timeout_s: float = 120.0):
    import httpx
    from concurrent.futures import ThreadPoolExecutor, as_completed

    query_url = f"{url}/query"
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
                    r = client.post(query_url, json=payload, timeout=timeout_s)
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


RAG_TEST_QUERIES = [
    {
        "query": "What is a dog?",
        "expected_keywords": ["dog", "canine", "pet", "mammal", "animal"],
        "description": "Dog-related query"
    },
    {
        "query": "Tell me about cats",
        "expected_keywords": ["cat", "feline", "pet", "mammal", "animal"],
        "description": "Cat-related query"
    },
    {
        "query": "What do you know about hamsters?",
        "expected_keywords": ["hamster", "rodent", "pet", "small"],
        "description": "Hamster-related query"
    },
    {
        "query": "Explain artificial intelligence",
        "expected_keywords": ["ai", "artificial", "intelligence", "machine"],
        "description": "AI definition query"
    },
    {
        "query": "What is machine learning?",
        "expected_keywords": ["machine", "learning", "ml", "model", "algorithm"],
        "description": "ML definition query"
    },
]


def check_rag_accuracy(query_url: str, timeout_s: float = 60.0) -> dict:
    import httpx

    results = []
    retrieval_times = []

    with httpx.Client(timeout=timeout_s) as client:
        for test in RAG_TEST_QUERIES:
            try:
                start = time.perf_counter()
                r = client.post(query_url, json={"query": test["query"], "top_k": 3})
                retrieval_time = time.perf_counter() - start

                if r.status_code != 200:
                    results.append({
                        "query": test["query"],
                        "description": test["description"],
                        "success": False,
                        "has_sources": False,
                        "keyword_match": False,
                        "match_score": 0,
                        "error": r.text[:100]
                    })
                    continue

                data = r.json()
                answer = data.get("answer", "").lower()
                sources = data.get("sources", [])
                retrieval_times.append(retrieval_time)

                has_sources = len(sources) > 0
                sources_text = " ".join(sources).lower()
                all_text = (answer + " " + sources_text).lower()

                keyword_matches = sum(
                    1 for kw in test["expected_keywords"]
                    if kw.lower() in all_text
                )
                match_score = keyword_matches / len(test["expected_keywords"])
                keyword_match = match_score >= 0.3

                results.append({
                    "query": test["query"],
                    "description": test["description"],
                    "success": True,
                    "has_sources": has_sources,
                    "keyword_match": keyword_match,
                    "match_score": round(match_score, 2),
                    "sources_count": len(sources),
                    "retrieval_time_ms": round(retrieval_time * 1000, 2)
                })
            except Exception as e:
                results.append({
                    "query": test["query"],
                    "description": test["description"],
                    "success": False,
                    "has_sources": False,
                    "keyword_match": False,
                    "match_score": 0,
                    "error": str(e)[:100]
                })

    total = len(results)
    successful = sum(1 for r in results if r["success"])
    with_sources = sum(1 for r in results if r["has_sources"])
    keyword_matches = sum(1 for r in results if r["keyword_match"])
    avg_retrieval_time = sum(retrieval_times) / len(retrieval_times) if retrieval_times else 0

    return {
        "total_queries": total,
        "successful": successful,
        "has_sources": with_sources,
        "keyword_matches": keyword_matches,
        "rag_accuracy_percent": round((keyword_matches / total) * 100, 1) if total else 0,
        "sources_coverage_percent": round((with_sources / total) * 100, 1) if total else 0,
        "avg_retrieval_time_ms": round(avg_retrieval_time * 1000, 2),
        "details": results
    }


def run_single_benchmark(label: str, workers: int, model: str,
                         requests: int, concurrency: int,
                         nginx_strategy: str = "round_robin",
                         ollama_num_gpu: str = "",
                         ollama_ctx: str = "",
                         ollama_batch: str = "",
                         embedding_model: str = "nomic-embed-text:latest"):
    log(f"\n{'='*60}")
    log(f"BENCHMARK: {label}")
    log(f"  workers={workers}, model={model}, concurrency={concurrency}")
    log(f"  strategy={nginx_strategy}, num_gpu={ollama_num_gpu or 'default'}")
    log(f"{'='*60}")

    procs = []

    nginx_exe = ROOT / "lb" / "nginx" / "nginx.exe"
    nginx_dir = ROOT / "lb" / "nginx"
    try:
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
                "MAX_CONCURRENT_TASKS": str(max(10, concurrency)),
                "BACKPRESSURE_QUEUE_SIZE": str(max(50, concurrency * 3)),
                "CACHE_SIZE": "500",
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

        log("All workers ready. Running load test...")
        result = run_load_test(requests, concurrency)

        log("Testing RAG accuracy...")
        rag_result = check_rag_accuracy("http://127.0.0.1:8000/query")
        result["rag_accuracy"] = rag_result

        result["label"] = label
        result["config"] = {
            "workers": workers,
            "model": model,
            "concurrency": concurrency,
            "strategy": nginx_strategy,
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
        models = ["smollm:135m"]

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
                label = f"model={model} workers={wc} concurrency={cc} rr"
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
                )
                if r:
                    results.append(r)
                    _print_result(r)

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

    rag = r.get("rag_accuracy", {})
    if rag:
        print(f"  RAG Accuracy: {rag['rag_accuracy_percent']}% ({rag['keyword_matches']}/{rag['total_queries']} queries matched)")
        print(f"  Sources Coverage: {rag['sources_coverage_percent']}% ({rag['has_sources']}/{rag['total_queries']})")
        print(f"  Avg Retrieval Time: {rag['avg_retrieval_time_ms']}ms")


def _print_summary(results):
    print(f"\n{'='*60}")
    print("BENCHMARK SUMMARY")
    print(f"{'='*60}")
    print(f"{'Label':<45} {'Throughput':>10} {'RAG Acc':>8} {'Avg Lat':>10} {'Err%':>8}")
    print("-" * 85)
    for r in results:
        label = r.get("label", "")[:45]
        thr = f"{r['throughput_rps']}r/s"
        rag_acc = r.get("rag_accuracy", {}).get("rag_accuracy_percent", 0)
        rag_str = f"{rag_acc:.0f}%" if rag_acc else "-"
        avg = f"{r['avg_latency_s']:.3f}s" if r['avg_latency_s'] else "-"
        err = f"{r['error_rate']:.1f}%"
        print(f"{label:<45} {thr:>10} {rag_str:>8} {avg:>10} {err:>8}")


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
    args = parser.parse_args()

    target = args.model or "smollm:135m"
    if not check_ollama(target):
        sys.exit(1)

    if not setup_nginx():
        sys.exit(1)

    if not start_nginx():
        sys.exit(1)

    try:
        if args.single:
            r = run_single_benchmark(
                label="single-test",
                workers=args.workers or 2,
                model=args.model or "smollm:135m",
                requests=args.requests,
                concurrency=args.concurrency or 10,
                ollama_num_gpu=args.num_gpu,
                ollama_ctx=args.ctx,
                ollama_batch=args.batch,
                embedding_model=args.embedding_model,
            )
            if r:
                _print_result(r)
                out = ROOT / "benchmark_result_latest.json"
                out.write_text(json.dumps(r, indent=2))
                log(f"Result saved to {out}")
        else:
            run_benchmark_suite(args)
    finally:
        stop_nginx()


if __name__ == "__main__":
    main()
