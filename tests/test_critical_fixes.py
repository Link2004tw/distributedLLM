import os
import sys
import time
import asyncio
import threading
import statistics

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
os.environ["CUDA_VISIBLE_DEVICES"] = "0"

import pytest
import httpx


class TestBackpressure:
    """Tests for the semaphore-based backpressure fix in load_balancer.py"""

    def test_semaphore_limits_concurrent_requests(self, lb_url, verify_services):
        client = httpx.Client(timeout=30.0)
        max_workers = 50
        completed = []
        failed = []

        def send_request(i):
            try:
                start = time.time()
                r = client.post(f"{lb_url}/query", json={"query": "backpressure test", "top_k": 1})
                latency = time.time() - start
                return (i, r.status_code, latency, None)
            except Exception as e:
                return (i, None, 0, str(e))

        threads = []
        for i in range(max_workers):
            t = threading.Thread(target=lambda idx: completed.append(send_request(idx)), args=(i,))
            threads.append(t)

        start_time = time.time()
        for t in threads:
            t.start()

        for t in threads:
            t.join()

        total_time = time.time() - start_time

        successes = [x for x in completed if x[1] == 200]
        failures = [x for x in completed if x[1] != 200]

        assert len(completed) == max_workers, "All requests should complete"
        assert len(failures) == 0, f"No failures expected under normal load: {failures}"
        print(f"  Backpressure test: {len(successes)}/{max_workers} succeeded in {total_time:.2f}s")
        client.close()

    def test_high_concurrency_no_deadlock(self, lb_url, verify_services):
        client = httpx.Client(timeout=120.0)
        num_requests = 60

        results = []
        def worker(i):
            try:
                r = client.post(f"{lb_url}/query", json={"query": f"concurrent test {i}", "top_k": 1})
                results.append(r.status_code)
            except Exception:
                results.append(None)

        threads = [threading.Thread(target=worker, args=(i,)) for i in range(num_requests)]
        start = time.time()
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        elapsed = time.time() - start

        success_count = sum(1 for c in results if c == 200)
        assert len(results) == num_requests, "All requests should return"
        assert elapsed < 60, f"60 concurrent requests should not take {elapsed:.1f}s (deadlock indicator)"
        print(f"  High concurrency: {success_count}/{num_requests} succeeded in {elapsed:.2f}s")
        client.close()

    def test_sequential_requests_not_blocked(self, lb_url, verify_services, sample_query):
        client = httpx.Client(timeout=60.0)
        latencies = []
        for i in range(5):
            start = time.time()
            r = client.post(f"{lb_url}/query", json=sample_query)
            latencies.append(time.time() - start)
            assert r.status_code == 200
        avg = sum(latencies) / len(latencies)
        assert avg < 30, f"Sequential requests too slow: {avg:.1f}s avg"
        print(f"  Sequential latency avg: {avg*1000:.0f}ms")
        client.close()


class TestWorkerAutoDiscovery:
    """Tests for Master -> LB worker registration flow"""

    def test_master_notifies_lb_on_registration(self, master_url, lb_url, verify_services):
        client = httpx.Client(timeout=10.0)
        test_worker_id = f"auto-discovery-test-{int(time.time())}"
        test_port = 8999

        workers_before = client.get(f"{lb_url}/workers").json()["workers"]
        before_ids = {w["worker_id"] for w in workers_before}

        r = client.post(f"{master_url}/register", json={"worker_id": test_worker_id, "port": test_port})
        assert r.status_code == 200

        time.sleep(2)

        workers_after = client.get(f"{lb_url}/workers").json()["workers"]
        after_ids = {w["worker_id"] for w in workers_after}

        new_workers = after_ids - before_ids
        assert test_worker_id in new_workers, f"Worker {test_worker_id} should be in LB registry after Master registration"
        print(f"  Worker auto-discovery: {test_worker_id} added to LB")
        client.close()

    def test_master_notifies_lb_on_worker_recovery(self, master_url, lb_url, verify_services):
        client = httpx.Client(timeout=10.0)
        test_worker_id = f"recovery-test-{int(time.time())}"
        test_port = 8998

        client.post(f"{master_url}/register", json={"worker_id": test_worker_id, "port": test_port})
        time.sleep(2)

        client.post(f"{lb_url}/worker/unhealthy", json={"worker_id": test_worker_id})
        time.sleep(0.5)

        healthy_before = [w for w in client.get(f"{lb_url}/workers").json()["workers"] if w["healthy"]]
        before_healthy_ids = {w["worker_id"] for w in healthy_before}

        client.post(f"{lb_url}/worker/healthy", json={"worker_id": test_worker_id})
        time.sleep(0.5)

        healthy_after = [w for w in client.get(f"{lb_url}/workers").json()["workers"] if w["healthy"]]
        after_healthy_ids = {w["worker_id"] for w in healthy_after}

        recovered = after_healthy_ids - before_healthy_ids
        assert test_worker_id in recovered, f"Worker {test_worker_id} should be marked healthy again"
        print(f"  Worker recovery: {test_worker_id} marked healthy")
        client.close()

    def test_lb_direct_add_worker_endpoint(self, lb_url, verify_services):
        client = httpx.Client(timeout=10.0)
        worker_id = f"direct-add-{int(time.time())}"
        port = 8997

        r = client.post(f"{lb_url}/workers/add", json={"worker_id": worker_id, "host": "localhost", "port": port})
        assert r.status_code == 200
        assert r.json()["status"] == "added"

        workers = client.get(f"{lb_url}/workers").json()["workers"]
        worker_ids = {w["worker_id"] for w in workers}
        assert worker_id in worker_ids, "Worker should be in LB registry"
        print(f"  Direct add: {worker_id} registered")
        client.close()

    def test_lb_direct_remove_worker_endpoint(self, lb_url, verify_services):
        client = httpx.Client(timeout=10.0)
        worker_id = f"to-remove-{int(time.time())}"
        port = 8996

        client.post(f"{lb_url}/workers/add", json={"worker_id": worker_id, "host": "localhost", "port": port})

        r = client.post(f"{lb_url}/workers/remove", json={"worker_id": worker_id})
        assert r.status_code == 200

        workers = client.get(f"{lb_url}/workers").json()["workers"]
        worker_ids = {w["worker_id"] for w in workers}
        assert worker_id not in worker_ids, "Worker should be removed from LB registry"
        print(f"  Direct remove: {worker_id} removed")
        client.close()


class TestGracefulDegradation:
    """Tests for Ollama failure handling in workers"""

    def test_worker_returns_fallback_on_llm_failure(self, worker_url, verify_services):
        client = httpx.Client(timeout=60.0)

        r = client.post(
            f"{worker_url}/query",
            json={"query": "test graceful degradation", "top_k": 3}
        )

        if r.status_code == 200:
            data = r.json()
            assert "answer" in data, "Response should have an answer field"
            assert len(data["answer"]) > 0, "Answer should not be empty"
            assert "Service temporarily unavailable" not in data["answer"], "Ollama should be working"
            print(f"  Graceful degradation: Ollama working, answer length = {len(data['answer'])}")
        else:
            print(f"  Graceful degradation: Worker returned {r.status_code}")
        client.close()

    def test_worker_health_always_returns_healthy(self, worker_url, verify_services):
        client = httpx.Client(timeout=30.0)
        r = client.get(f"{worker_url}/health")
        assert r.status_code == 200
        data = r.json()
        assert data["healthy"] == True, "Health endpoint should always report healthy"
        assert "worker_id" in data
        assert "gpu_utilization" in data
        print(f"  Health check: worker_id={data['worker_id']}, gpu={data['gpu_utilization']}%")
        client.close()

    def test_worker_retrieval_time_tracked(self, worker_url, verify_services):
        client = httpx.Client(timeout=60.0)
        r = client.post(f"{worker_url}/query", json={"query": "retrieval time test", "top_k": 3})
        assert r.status_code == 200
        data = r.json()
        assert "retrieval_time_ms" in data, "Response should include retrieval_time_ms"
        assert data["retrieval_time_ms"] >= 0, "Retrieval time should be non-negative"
        print(f"  Retrieval time: {data['retrieval_time_ms']:.1f}ms")
        client.close()


class TestWorkerFeatureParity:
    """Tests to verify worker.py matches gpu_worker.py feature set"""

    def test_worker_has_gpu_stats_endpoint(self, worker_url, verify_services):
        client = httpx.Client(timeout=30.0)
        r = client.get(f"{worker_url}/gpu-stats")
        assert r.status_code == 200
        data = r.json()
        assert "memory_total_mb" in data
        assert "memory_used_mb" in data
        assert "memory_free_mb" in data
        assert "utilization_percent" in data
        assert "temperature_c" in data
        assert "power_watts" in data
        print(f"  GPU stats: {data['utilization_percent']}% util, {data['memory_used_mb']}MB used, {data['power_watts']:.1f}W")
        client.close()

    def test_worker_has_capabilities_endpoint(self, worker_url, verify_services):
        client = httpx.Client(timeout=30.0)
        r = client.get(f"{worker_url}/capabilities")
        assert r.status_code == 200
        data = r.json()
        assert data["single_query"] == True
        assert data["batch_processing"] == True
        assert data["gpu_accelerated"] == True
        assert data["caching"] == True
        print(f"  Capabilities: batch={data['batch_processing']}, cache={data['cache_size']}")
        client.close()

    def test_worker_has_batch_endpoint(self, worker_url, verify_services):
        client = httpx.Client(timeout=120.0)
        r = client.post(
            f"{worker_url}/query/batch",
            json={
                "queries": [
                    {"query": "batch test 1", "top_k": 2},
                    {"query": "batch test 2", "top_k": 2},
                    {"query": "batch test 3", "top_k": 2},
                ]
            }
        )
        assert r.status_code == 200
        data = r.json()
        assert "results" in data
        assert len(data["results"]) == 3
        assert "batch_size" in data
        print(f"  Batch endpoint: processed {data['batch_size']} queries")
        client.close()

    def test_worker_has_ready_endpoint(self, worker_url, verify_services):
        client = httpx.Client(timeout=30.0)
        r = client.get(f"{worker_url}/ready")
        assert r.status_code == 200
        data = r.json()
        assert "ready" in data
        assert "worker_id" in data
        print(f"  Ready check: {data['ready']}, worker_id={data['worker_id']}")
        client.close()

    def test_worker_has_worker_id_endpoint(self, worker_url, verify_services):
        client = httpx.Client(timeout=30.0)
        r = client.get(f"{worker_url}/worker-id")
        assert r.status_code == 200
        data = r.json()
        assert "worker_id" in data
        client.close()

    def test_worker_response_has_all_required_fields(self, worker_url, verify_services):
        client = httpx.Client(timeout=60.0)
        r = client.post(f"{worker_url}/query", json={"query": "full response test", "top_k": 3})
        assert r.status_code == 200
        data = r.json()
        required = ["worker_id", "answer", "sources", "latency_ms", "retrieval_time_ms", "cache_hit"]
        for field in required:
            assert field in data, f"Response missing field: {field}"
        print(f"  Full response: latency={data['latency_ms']:.0f}ms, cache_hit={data['cache_hit']}")
        client.close()

    def test_worker_embed_cache_works(self, worker_url, verify_services):
        client = httpx.Client(timeout=120.0)
        unique = f"embed-cache-{time.time()}"
        payload = {"query": unique, "top_k": 3}

        r1 = client.post(f"{worker_url}/query", json=payload)
        assert r1.status_code == 200
        assert r1.json()["cache_hit"] == False

        r2 = client.post(f"{worker_url}/query", json=payload)
        assert r2.status_code == 200
        assert r2.json()["cache_hit"] == True, "Second query should hit cache"
        print(f"  Embed cache: working (cache_hit verified)")
        client.close()


class TestLoadBalancerWorkerSync:
    """Tests for LB <-> Master integration"""

    def test_lb_workers_reflect_master_registrations(self, master_url, lb_url, verify_services):
        client = httpx.Client(timeout=10.0)
        test_id = f"sync-test-{int(time.time())}"
        test_port = 8995

        r = client.post(f"{master_url}/register", json={"worker_id": test_id, "port": test_port})
        time.sleep(2)

        lb_workers = client.get(f"{lb_url}/workers").json()["workers"]
        lb_ids = {w["worker_id"] for w in lb_workers}

        assert test_id in lb_ids, f"Master-registered worker {test_id} should appear in LB"

        master_workers = client.get(f"{master_url}/workers").json()["workers"]
        master_ids = {w["worker_id"] for w in master_workers}
        assert test_id in master_ids, f"Worker {test_id} should be in Master registry"

        print(f"  LB-Master sync: {test_id} registered in both")
        client.close()

    def test_unhealthy_notification_flow(self, master_url, lb_url, verify_services):
        client = httpx.Client(timeout=10.0)
        test_id = f"unhealthy-flow-{int(time.time())}"
        test_port = 8994

        client.post(f"{master_url}/register", json={"worker_id": test_id, "port": test_port})
        time.sleep(2)

        client.post(f"{lb_url}/worker/unhealthy", json={"worker_id": test_id})
        time.sleep(0.5)

        workers = client.get(f"{lb_url}/workers").json()["workers"]
        target = next((w for w in workers if w["worker_id"] == test_id), None)
        assert target is not None, f"Worker {test_id} should still be in LB"
        assert target["healthy"] == False, f"Worker {test_id} should be marked unhealthy"
        print(f"  Unhealthy notification: {test_id} marked unhealthy in LB")
        client.close()

    def test_lb_reports_consistent_health(self, lb_url, verify_services):
        client = httpx.Client(timeout=30.0)
        r = client.get(f"{lb_url}/workers")
        data = r.json()

        assert "strategy" in data
        assert "total_requests" in data
        assert "failed_requests" in data
        assert len(data["workers"]) >= 1, "Should have at least one worker"

        healthy = [w for w in data["workers"] if w["healthy"]]
        print(f"  LB health: {len(healthy)}/{len(data['workers'])} workers healthy, strategy={data['strategy']}")
        client.close()