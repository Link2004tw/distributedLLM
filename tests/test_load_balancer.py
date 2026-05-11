import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
os.environ["CUDA_VISIBLE_DEVICES"] = "0"

import pytest
import httpx


@pytest.mark.health
class TestLoadBalancerHealth:
    def test_health_endpoint(self, lb_url, verify_services):
        client = httpx.Client(timeout=30.0)
        response = client.get(f"{lb_url}/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        client.close()

    def test_workers_endpoint(self, lb_url, verify_services):
        client = httpx.Client(timeout=30.0)
        response = client.get(f"{lb_url}/workers")
        assert response.status_code == 200
        data = response.json()
        assert "workers" in data
        assert "strategy" in data
        client.close()

    def test_stats_endpoint(self, lb_url, verify_services):
        client = httpx.Client(timeout=30.0)
        response = client.get(f"{lb_url}/stats")
        assert response.status_code == 200
        data = response.json()
        assert "total_workers" in data
        assert "healthy_workers" in data
        assert data["healthy_workers"] >= 1
        client.close()

    def test_strategy_endpoint_get(self, lb_url, verify_services):
        client = httpx.Client(timeout=30.0)
        response = client.get(f"{lb_url}/strategy")
        assert response.status_code == 200
        data = response.json()
        assert "strategy" in data
        client.close()


@pytest.mark.load
class TestLoadBalancerRouting:
    def test_round_robin_strategy(self, lb_url, verify_services, sample_queries):
        client = httpx.Client(timeout=120.0)

        client.post(f"{lb_url}/strategy", json={"strategy": "round_robin"})
        response = client.post(f"{lb_url}/query", json=sample_queries[0])
        assert response.status_code == 200

        client.close()

    def test_least_connections_strategy(self, lb_url, verify_services, sample_query):
        client = httpx.Client(timeout=120.0)
        response = client.get(f"{lb_url}/workers")
        if response.status_code != 200:
            client.close()
            pytest.skip("LB not available")
        
        response = client.post(f"{lb_url}/strategy", json={"strategy": "least_connections"})
        if response.status_code != 200:
            client.close()
            pytest.skip("Strategy change failed")
        
        response = client.post(f"{lb_url}/query", json=sample_query)
        if response.status_code == 503:
            client.close()
            pytest.skip("No healthy workers available")
        assert response.status_code == 200
        client.close()

    def test_hybrid_strategy(self, lb_url, verify_services, sample_query):
        client = httpx.Client(timeout=120.0)
        response = client.get(f"{lb_url}/workers")
        if response.status_code != 200:
            client.close()
            pytest.skip("LB not available")
        
        response = client.post(f"{lb_url}/strategy", json={"strategy": "hybrid"})
        if response.status_code != 200:
            client.close()
            pytest.skip("Strategy change failed")
        
        response = client.post(f"{lb_url}/query", json=sample_query)
        if response.status_code == 503:
            client.close()
            pytest.skip("No healthy workers available")
        assert response.status_code == 200
        client.close()

    def test_gpu_aware_strategy(self, lb_url, verify_services, sample_query):
        client = httpx.Client(timeout=120.0)

        client.post(f"{lb_url}/strategy", json={"strategy": "gpu_aware"})
        response = client.post(f"{lb_url}/query", json=sample_query)
        assert response.status_code == 200

        client.close()

    def test_invalid_strategy_rejected(self, lb_url, verify_services, sample_query):
        client = httpx.Client(timeout=30.0)
        response = client.post(f"{lb_url}/strategy", json={"strategy": "invalid"})
        assert response.status_code == 400
        client.close()


@pytest.mark.load
class TestLoadBalancerQuery:
    def test_query_returns_answer(self, lb_url, verify_services, sample_query):
        client = httpx.Client(timeout=120.0)
        response = client.post(f"{lb_url}/query", json=sample_query)
        assert response.status_code == 200
        data = response.json()
        assert "answer" in data
        assert "latency_ms" in data
        client.close()

    def test_query_uses_worker_gpu_stats(self, lb_url, verify_services, sample_query):
        client = httpx.Client(timeout=120.0)

        client.post(f"{lb_url}/query", json=sample_query)

        response = client.get(f"{lb_url}/workers")
        data = response.json()

        for worker in data["workers"]:
            if worker["healthy"]:
                assert "gpu_memory_mb" in worker
                assert worker["gpu_memory_mb"] >= 0

        client.close()


@pytest.mark.health
class TestLoadBalancerWorkerManagement:
    def test_mark_worker_unhealthy(self, lb_url, verify_services):
        client = httpx.Client(timeout=30.0)
        response = client.post(
            f"{lb_url}/worker/unhealthy",
            json={"worker_id": "worker-1"}
        )
        assert response.status_code == 200
        client.close()

    def test_mark_worker_healthy(self, lb_url, verify_services):
        client = httpx.Client(timeout=30.0)
        response = client.post(
            f"{lb_url}/worker/healthy",
            json={"worker_id": "worker-1"}
        )
        assert response.status_code == 200
        client.close()

    def test_add_worker(self, lb_url, verify_services):
        client = httpx.Client(timeout=30.0)
        response = client.post(
            f"{lb_url}/workers/add",
            json={"worker_id": "worker-test", "host": "localhost", "port": 8099}
        )
        assert response.status_code == 200
        client.close()

    def test_remove_worker(self, lb_url, verify_services):
        client = httpx.Client(timeout=30.0)
        response = client.post(
            f"{lb_url}/workers/remove",
            json={"worker_id": "worker-4"}
        )
        assert response.status_code == 200
        client.close()