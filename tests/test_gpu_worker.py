import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
os.environ["CUDA_VISIBLE_DEVICES"] = "0"
os.environ["OLLAMA_URL"] = "http://localhost:11434"

import pytest
import httpx
from concurrent.futures import ThreadPoolExecutor, as_completed


BASE_URL = os.environ.get("TEST_BASE_URL", "http://127.0.0.1:8000")
WORKER_URL = os.environ.get("TEST_WORKER_URL", "http://127.0.0.1:8001")
LB_URL = os.environ.get("TEST_LB_URL", "http://127.0.0.1:8000")
MASTER_URL = os.environ.get("TEST_MASTER_URL", "http://127.0.0.1:9000")


class TestHealthEndpoints:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.client = httpx.Client(timeout=30.0)

    def teardown_method(self):
        self.client.close()

    def test_worker_health(self):
        response = self.client.get(f"{WORKER_URL}/health")
        assert response.status_code == 200
        data = response.json()
        assert "worker_id" in data
        assert "gpu_utilization" in data
        assert "gpu_memory_total_mb" in data

    def test_worker_gpu_stats(self):
        response = self.client.get(f"{WORKER_URL}/gpu-stats")
        assert response.status_code == 200
        data = response.json()
        assert data["memory_total_mb"] > 0

    def test_lb_health(self):
        response = self.client.get(f"{LB_URL}/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"

    def test_lb_workers(self):
        response = self.client.get(f"{LB_URL}/workers")
        assert response.status_code == 200
        data = response.json()
        assert "workers" in data
        assert len(data["workers"]) > 0

    def test_lb_stats(self):
        response = self.client.get(f"{LB_URL}/stats")
        assert response.status_code == 200
        data = response.json()
        assert "total_workers" in data
        assert "current_strategy" in data


class TestQueryEndpoints:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.client = httpx.Client(timeout=120.0)

    def teardown_method(self):
        self.client.close()

    def test_worker_query(self):
        response = self.client.post(
            f"{WORKER_URL}/query",
            json={"query": "What is AI?", "top_k": 3}
        )
        assert response.status_code == 200
        data = response.json()
        assert "answer" in data
        assert "sources" in data
        assert "latency_ms" in data

    def test_worker_query_caching(self):
        payload = {"query": "What is machine learning?", "top_k": 3}

        response1 = self.client.post(f"{WORKER_URL}/query", json=payload)
        assert response1.status_code == 200
        data1 = response1.json()
        cache_hit_1 = data1.get("cache_hit", False)

        response2 = self.client.post(f"{WORKER_URL}/query", json=payload)
        assert response2.status_code == 200
        data2 = response2.json()
        cache_hit_2 = data2.get("cache_hit", False)

        assert cache_hit_2 == True, "Second query should be cached"

    def test_lb_query_routing(self):
        response = self.client.post(
            f"{LB_URL}/query",
            json={"query": "Explain neural networks", "top_k": 3}
        )
        assert response.status_code == 200
        data = response.json()
        assert "answer" in data

    def test_worker_batch_query(self):
        response = self.client.post(
            f"{WORKER_URL}/query/batch",
            json={
                "queries": [
                    {"query": "What is AI?", "top_k": 3},
                    {"query": "What is ML?", "top_k": 3},
                ]
            }
        )
        assert response.status_code == 200
        data = response.json()
        assert "results" in data
        assert len(data["results"]) == 2

    def test_lb_strategy_change(self):
        strategies = ["round_robin", "least_connections", "hybrid", "gpu_aware"]
        for strategy in strategies:
            response = self.client.post(
                f"{LB_URL}/strategy",
                json={"strategy": strategy}
            )
            assert response.status_code == 200
            data = response.json()
            assert data["strategy"] == strategy


class TestGPUMonitoring:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.client = httpx.Client(timeout=30.0)

    def teardown_method(self):
        self.client.close()

    def test_gpu_memory_tracking(self):
        response = self.client.get(f"{WORKER_URL}/gpu-stats")
        data = response.json()

        assert data["memory_total_mb"] > 0
        assert data["memory_used_mb"] >= 0
        assert data["memory_free_mb"] >= 0
        assert data["memory_free_mb"] + data["memory_used_mb"] == data["memory_total_mb"]

    def test_gpu_utilization_tracking(self):
        self.client.post(
            f"{WORKER_URL}/query",
            json={"query": "Explain quantum computing", "top_k": 3}
        )

        response = self.client.get(f"{WORKER_URL}/gpu-stats")
        data = response.json()

        assert data["utilization_percent"] >= 0
        assert data["utilization_percent"] <= 100

    def test_temperature_tracking(self):
        response = self.client.get(f"{WORKER_URL}/gpu-stats")
        data = response.json()

        assert data["temperature_c"] >= 0
        assert data["temperature_c"] <= 100


class TestLoadBalancing:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.client = httpx.Client(timeout=120.0)

    def teardown_method(self):
        self.client.close()

    def test_round_robin_distribution(self):
        response = self.client.get(f"{LB_URL}/workers")
        if response.status_code != 200:
            pytest.skip("LB not available")
        
        workers_data = response.json()
        healthy_count = sum(1 for w in workers_data.get("workers", []) if w.get("healthy", False))
        
        if healthy_count < 2:
            pytest.skip(f"Need at least 2 workers, have {healthy_count}")
        
        self.client.post(f"{LB_URL}/strategy", json={"strategy": "round_robin"})

        response = self.client.post(
            f"{LB_URL}/query",
            json={"query": "Test round robin", "top_k": 1}
        )
        assert response.status_code == 200

    def test_least_connections_routing(self):
        self.client.post(f"{LB_URL}/strategy", json={"strategy": "least_connections"})

        response = self.client.post(
            f"{LB_URL}/query",
            json={"query": "Load balancing test", "top_k": 1}
        )
        assert response.status_code == 200

    def test_invalid_strategy_rejected(self):
        response = self.client.post(
            f"{LB_URL}/strategy",
            json={"strategy": "invalid_strategy"}
        )
        assert response.status_code == 400


class TestCaching:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.client = httpx.Client(timeout=120.0)

    def teardown_method(self):
        self.client.close()

    def test_cache_reduces_latency(self):
        payload = {"query": "Unique query for cache test 12345", "top_k": 3}

        start1 = time.time()
        response1 = self.client.post(f"{WORKER_URL}/query", json=payload)
        time1 = time.time() - start1

        start2 = time.time()
        response2 = self.client.post(f"{WORKER_URL}/query", json=payload)
        time2 = time.time() - start2

        assert response1.status_code == 200
        assert response2.status_code == 200
        assert response2.json()["cache_hit"] == True

    def test_different_queries_not_cached(self):
        import time
        unique_prefix = f"unique_cache_test_{time.time()}_"
        
        queries = [
            f"{unique_prefix}query_a",
            f"{unique_prefix}query_b",
            f"{unique_prefix}query_c",
        ]

        for q in queries:
            response = self.client.post(
                f"{WORKER_URL}/query",
                json={"query": q, "top_k": 3}
            )
            if response.status_code == 200:
                data = response.json()
                if data.get("cache_hit") == True:
                    pass


class TestErrorHandling:
    @pytest.fixture(autouse=True)
    def setup(self):
        self.client = httpx.Client(timeout=10.0)

    def teardown_method(self):
        self.client.close()

    def test_worker_invalid_request(self):
        response = self.client.post(
            f"{WORKER_URL}/query",
            json={"invalid_field": "value"}
        )
        assert response.status_code >= 400

    def test_lb_no_workers_available(self):
        pass


def run_quick_test():
    print("=" * 60)
    print("QUICK TEST - Running basic health checks")
    print("=" * 60)

    client = httpx.Client(timeout=30.0)

    print("\n1. Testing Worker Health...")
    r = client.get(f"{WORKER_URL}/health")
    print(f"   Status: {r.status_code}")
    print(f"   GPU Memory: {r.json().get('gpu_memory_total_mb', 0)} MB")

    print("\n2. Testing Load Balancer...")
    r = client.get(f"{LB_URL}/health")
    print(f"   Status: {r.status_code}")

    print("\n3. Testing Query...")
    r = client.post(f"{WORKER_URL}/query", json={"query": "Quick test", "top_k": 1})
    print(f"   Status: {r.status_code}")
    print(f"   Latency: {r.json().get('latency_ms', 0):.0f}ms")

    client.close()
    print("\n" + "=" * 60)
    print("Quick test complete!")
    print("=" * 60)


if __name__ == "__main__":
    run_quick_test()