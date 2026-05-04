import threading
import time
import uuid
import statistics
from collections import defaultdict
from typing import List
import httpx


LOAD_BALANCER_URL = "http://localhost:8000"
NUM_USERS = 1000
Queries = [
    "What is the capital of France?",
    "How do I install Python 3.10?",
    "Explain quantum computing in simple terms.",
    "What are the benefits of exercise?",
    "Write a Python function to reverse a string.",
    "What is the meaning of life?",
    "How does photosynthesis work?",
    "What is machine learning?",
    "Explain the theory of relativity.",
    "What is the best programming language for AI?",
]


latencies: List[float] = []
errors: List[str] = []
lock = threading.Lock()


def send_request(user_id: str):
    query = Queries[int(uuid.uuid4().int) % len(Queries)]
    start_time = time.time()

    try:
        with httpx.Client(timeout=30.0) as client:
            response = client.post(
                f"{LOAD_BALANCER_URL}/query",
                json={"query": query, "user_id": user_id},
            )
            latency = (time.time() - start_time) * 1000

            with lock:
                latencies.append(latency)

            if response.status_code != 200:
                with lock:
                    errors.append(f"User {user_id}: HTTP {response.status_code}")
    except Exception as e:
        latency = (time.time() - start_time) * 1000
        with lock:
            latencies.append(latency)
            errors.append(f"User {user_id}: {str(e)}")


def run_load_test():
    print(f"Starting load test with {NUM_USERS} concurrent users...")
    print(f"Target: {LOAD_BALANCER_URL}")

    threads = []
    start = time.time()

    for i in range(NUM_USERS):
        user_id = f"user-{i:04d}"
        t = threading.Thread(target=send_request, args=(user_id,))
        threads.append(t)
        t.start()

        if i % 100 == 0 and i > 0:
            time.sleep(0.1)

    for t in threads:
        t.join()

    duration = time.time() - start

    print("\n" + "=" * 50)
    print("LOAD TEST RESULTS")
    print("=" * 50)
    print(f"Total requests: {NUM_USERS}")
    print(f"Duration: {duration:.2f}s")
    print(f"Throughput: {NUM_USERS / duration:.2f} req/s")

    if latencies:
        latencies_sorted = sorted(latencies)
        p50 = latencies_sorted[len(latencies_sorted) // 2]
        p95 = latencies_sorted[int(len(latencies_sorted) * 0.95)]
        p99 = latencies_sorted[int(len(latencies_sorted) * 0.99)]

        print(f"\nLatency (ms):")
        print(f"  Mean: {statistics.mean(latencies):.2f}")
        print(f"  Median: {statistics.median(latencies):.2f}")
        print(f"  P50: {p50:.2f}")
        print(f"  P95: {p95:.2f}")
        print(f"  P99: {p99:.2f}")
        print(f"  Min: {min(latencies):.2f}")
        print(f"  Max: {max(latencies):.2f}")

    if errors:
        print(f"\nErrors: {len(errors)}")
        for err in errors[:10]:
            print(f"  {err}")
    else:
        print(f"\nErrors: 0")

    print("=" * 50)


if __name__ == "__main__":
    run_load_test()