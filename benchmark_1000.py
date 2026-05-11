"""Benchmark: 1000 concurrent requests to the Tailscale distributed system."""

import asyncio
import time
import statistics
from typing import List

import httpx

TARGET_URL = "http://100.103.28.116:8000/query"
NUM_REQUESTS = 1000
CONCURRENCY = 100
TIMEOUT = 120.0

SAMPLE_QUERIES = [
    "What is distributed computing?",
    "Explain load balancing.",
    "What is RAG?",
    "How does fault tolerance work?",
    "What is the role of the master node?",
    "Explain round robin routing.",
    "Explain least connections routing.",
    "What happens if one worker fails?",
    "How can throughput be improved?",
    "Summarize the system architecture.",
]


async def send(client: httpx.AsyncClient, sem: asyncio.Semaphore, idx: int) -> dict:
    query = SAMPLE_QUERIES[idx % len(SAMPLE_QUERIES)]
    payload = {"query": query, "top_k": 1}

    async with sem:
        start = time.perf_counter()
        try:
            resp = await client.post(TARGET_URL, json=payload, timeout=TIMEOUT)
            elapsed = time.perf_counter() - start
            return {
                "success": resp.status_code == 200,
                "latency": elapsed,
                "status": resp.status_code,
                "error": None if resp.status_code == 200 else resp.text[:200],
            }
        except Exception as e:
            elapsed = time.perf_counter() - start
            return {"success": False, "latency": elapsed, "status": None, "error": str(e)}


async def main():
    print("=" * 60)
    print("DISTRIBUTED LLM — BENCHMARK 1000")
    print("=" * 60)
    print(f"Target : {TARGET_URL}")
    print(f"Requests: {NUM_REQUESTS}")
    print(f"Concurrency: {CONCURRENCY}")
    print(f"Timeout: {TIMEOUT}s")
    print("=" * 60)

    limits = httpx.Limits(max_connections=CONCURRENCY, max_keepalive_connections=CONCURRENCY)
    sem = asyncio.Semaphore(CONCURRENCY)
    results: List[dict] = []

    async with httpx.AsyncClient(limits=limits, timeout=TIMEOUT) as client:
        tasks = [send(client, sem, i) for i in range(NUM_REQUESTS)]

        test_start = time.perf_counter()
        completed = 0

        for coro in asyncio.as_completed(tasks):
            result = await coro
            results.append(result)
            completed += 1
            if completed % 100 == 0 or completed == NUM_REQUESTS:
                print(f"  Completed {completed}/{NUM_REQUESTS}")

        total_time = time.perf_counter() - test_start

    successful = [r for r in results if r["success"]]
    failed = [r for r in results if not r["success"]]
    latencies = [r["latency"] for r in successful]

    success_count = len(successful)
    failed_count = len(failed)
    throughput = NUM_REQUESTS / total_time if total_time > 0 else 0
    error_rate = (failed_count / NUM_REQUESTS) * 100 if NUM_REQUESTS > 0 else 0

    print()
    print("=" * 60)
    print("RESULTS")
    print("=" * 60)
    print(f"Total requests      : {NUM_REQUESTS}")
    print(f"Successful          : {success_count}")
    print(f"Failed              : {failed_count}")
    print(f"Error rate          : {error_rate:.2f}%")
    print(f"Total time          : {total_time:.2f}s")
    print(f"Throughput          : {throughput:.2f} req/s")

    if latencies:
        latencies_sorted = sorted(latencies)
        p50 = latencies_sorted[int(len(latencies_sorted) * 0.50)]
        p95 = latencies_sorted[int(len(latencies_sorted) * 0.95)]
        p99 = latencies_sorted[int(len(latencies_sorted) * 0.99)]

        print()
        print("LATENCY")
        print(f"Average             : {statistics.mean(latencies):.4f}s")
        print(f"Min                 : {min(latencies):.4f}s")
        print(f"Max                 : {max(latencies):.4f}s")
        print(f"P50                 : {p50:.4f}s")
        print(f"P95                 : {p95:.4f}s")
        print(f"P99                 : {p99:.4f}s")

    if failed:
        print()
        print("SAMPLE ERRORS")
        for r in failed[:5]:
            print(f"  Status: {r['status']}, Error: {r['error']}")

    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
