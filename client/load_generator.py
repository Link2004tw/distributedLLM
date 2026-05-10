# import threading
# from common.models import Request



# def simulate_user(scheduler,user_id):
#     request = Request(id=user_id, query=f"Query {user_id}")
#     response= scheduler.handle_request(request)
#     print (f"[Client] Response: {response['id']} | Latency: {response['latency']:.3f}s")

# def run_load_test(scheduler, num_users=1000):
#     threads = []
#     for i in range(num_users):
#         t = threading.Thread(target=simulate_user, args=(scheduler,i))
#         threads.append(t)
#         t.start()
#     for t in threads:
#         t.join()import time
import uuid
import time
import argparse
import statistics
from dataclasses import dataclass
from typing import Optional
from concurrent.futures import ThreadPoolExecutor, as_completed

import httpx


@dataclass
class RequestResult:
    success: bool
    latency: float
    status_code: Optional[int]
    error: Optional[str]


SAMPLE_QUERIES = [
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


def generate_request_id():
    return str(uuid.uuid4())


def send_request(client: httpx.Client, client_id: int, url: str, timeout: float) -> RequestResult:
    request_id = generate_request_id()

    payload = {
        "id": request_id,
        "request_id": request_id,
        "client_id": client_id,
        "query": SAMPLE_QUERIES[client_id % len(SAMPLE_QUERIES)]
    }

    start_time = time.perf_counter()

    try:
        response = client.post(
            url,
            json=payload,
            timeout=timeout
        )

        latency = time.perf_counter() - start_time

        if response.status_code == 200:
            return RequestResult(
                success=True,
                latency=latency,
                status_code=response.status_code,
                error=None
            )

        return RequestResult(
            success=False,
            latency=latency,
            status_code=response.status_code,
            error=response.text
        )

    except Exception as e:
        latency = time.perf_counter() - start_time

        return RequestResult(
            success=False,
            latency=latency,
            status_code=None,
            error=str(e)
        )


def percentile(values, percent):
    if not values:
        return 0

    values = sorted(values)
    index = int((percent / 100) * len(values)) - 1
    index = max(0, min(index, len(values) - 1))

    return values[index]


def run_load_test(total_requests: int, concurrency: int, base_url: str, timeout: float):
    query_url = f"{base_url}/query"

    print("=" * 60)
    print("CLIENT LOAD TEST STARTED")
    print("=" * 60)
    print(f"Target URL       : {query_url}")
    print(f"Total Requests   : {total_requests}")
    print(f"Concurrency      : {concurrency}")
    print(f"Timeout          : {timeout}s")
    print("=" * 60)

    results = []

    limits = httpx.Limits(
        max_connections=concurrency,
        max_keepalive_connections=concurrency
    )

    test_start = time.perf_counter()

    with httpx.Client(limits=limits) as client:
        with ThreadPoolExecutor(max_workers=concurrency) as executor:
            futures = [
                executor.submit(send_request, client, i, query_url, timeout)
                for i in range(total_requests)
            ]

            completed = 0

            for future in as_completed(futures):
                result = future.result()
                results.append(result)

                completed += 1
                if completed % 50 == 0 or completed == total_requests:
                    print(f"Completed {completed}/{total_requests} requests")

    total_time = time.perf_counter() - test_start

    successful_results = [r for r in results if r.success]
    failed_results = [r for r in results if not r.success]

    latencies = [r.latency for r in successful_results]

    success_count = len(successful_results)
    failed_count = len(failed_results)

    throughput = total_requests / total_time if total_time > 0 else 0
    error_rate = (failed_count / total_requests) * 100 if total_requests > 0 else 0

    print()
    print("=" * 60)
    print("LOAD TEST RESULTS")
    print("=" * 60)
    print(f"Total Requests      : {total_requests}")
    print(f"Successful Requests : {success_count}")
    print(f"Failed Requests     : {failed_count}")
    print(f"Error Rate          : {error_rate:.2f}%")
    print(f"Total Time          : {total_time:.2f}s")
    print(f"Throughput          : {throughput:.2f} requests/sec")

    if latencies:
        print()
        print("LATENCY METRICS")
        print(f"Average Latency     : {statistics.mean(latencies):.4f}s")
        print(f"Minimum Latency     : {min(latencies):.4f}s")
        print(f"Maximum Latency     : {max(latencies):.4f}s")
        print(f"P50 Latency         : {percentile(latencies, 50):.4f}s")
        print(f"P95 Latency         : {percentile(latencies, 95):.4f}s")
        print(f"P99 Latency         : {percentile(latencies, 99):.4f}s")
    else:
        print()
        print("No successful requests. Cannot calculate latency metrics.")

    if failed_results:
        print()
        print("SAMPLE ERRORS")
        for r in failed_results[:5]:
            print(f"- Status: {r.status_code}, Error: {r.error}")

    print("=" * 60)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Client Load Generator")

    parser.add_argument(
        "--requests",
        type=int,
        default=100,
        help="Total number of requests to send"
    )

    parser.add_argument(
        "--concurrency",
        type=int,
        default=20,
        help="Number of requests running at the same time"
    )

    parser.add_argument(
        "--url",
        type=str,
        default="http://127.0.0.1:8000",
        help="Base URL of the load balancer"
    )

    parser.add_argument(
        "--timeout",
        type=float,
        default=60.0,
        help="Timeout for each request"
    )

    args = parser.parse_args()

    run_load_test(
        total_requests=args.requests,
        concurrency=args.concurrency,
        base_url=args.url,
        timeout=args.timeout
    )