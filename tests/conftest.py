import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import pytest


@pytest.fixture(scope="session")
def worker_url():
    return os.environ.get("TEST_WORKER_URL", "http://127.0.0.1:8001")


@pytest.fixture(scope="session")
def lb_url():
    return os.environ.get("TEST_LB_URL", "http://127.0.0.1:8000")


@pytest.fixture(scope="session")
def master_url():
    return os.environ.get("TEST_MASTER_URL", "http://127.0.0.1:9000")


@pytest.fixture(scope="session")
def ollama_url():
    return os.environ.get("OLLAMA_URL", "http://localhost:11434")


@pytest.fixture
def sample_query():
    return {
        "query": "What is artificial intelligence?",
        "top_k": 3
    }


@pytest.fixture
def sample_queries():
    return [
        {"query": "What is machine learning?", "top_k": 3},
        {"query": "Explain neural networks", "top_k": 3},
        {"query": "What is deep learning?", "top_k": 3},
    ]


@pytest.fixture(scope="session")
def verify_services(worker_url, lb_url):
    import httpx

    client = httpx.Client(timeout=10.0)

    try:
        r = client.get(f"{worker_url}/health")
        assert r.status_code == 200, "Worker not responding"
    except Exception as e:
        pytest.skip(f"Worker not available: {e}")

    try:
        r = client.get(f"{lb_url}/health")
        assert r.status_code == 200, "Load Balancer not responding"
    except Exception as e:
        pytest.skip(f"Load Balancer not available: {e}")

    client.close()