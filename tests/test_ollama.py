import os
import time

os.environ["OLLAMA_URL"] = "http://localhost:11434"

import pytest
import httpx


class TestOllamaIntegration:
    models = []
    model_names = []

    @pytest.fixture(scope="class", autouse=True)
    def setup_class(self):
        client = httpx.Client(timeout=30.0)
        try:
            r = client.get("http://localhost:11434/api/tags")
            assert r.status_code == 200
            TestOllamaIntegration.models = r.json().get("models", [])
            TestOllamaIntegration.model_names = [m.get("name", "") for m in self.models]
        except Exception as e:
            pytest.skip(f"Ollama not available: {e}")
        finally:
            client.close()

    def test_ollama_responding(self):
        client = httpx.Client(timeout=30.0)
        r = client.get("http://localhost:11434/api/tags")
        assert r.status_code == 200
        client.close()

    def test_smollm2_model_available(self):
        assert "smollm:135m" in TestOllamaIntegration.model_names

    def test_nomic_embed_model_available(self):
        assert any("nomic" in name.lower() for name in TestOllamaIntegration.model_names)

    def test_generate_endpoint(self):
        client = httpx.Client(timeout=60.0)
        r = client.post(
            "http://localhost:11434/api/generate",
            json={"model": "smollm:135m", "prompt": "Hi", "stream": False}
        )
        assert r.status_code == 200
        data = r.json()
        assert "response" in data
        client.close()

    def test_embedding_endpoint(self):
        client = httpx.Client(timeout=60.0)
        r = client.post(
            "http://localhost:11434/api/embeddings",
            json={"model": "nomic-embed-text:latest", "prompt": "test text"}
        )
        assert r.status_code == 200
        data = r.json()
        assert "embedding" in data
        assert len(data["embedding"]) > 0
        client.close()

    def test_generate_with_longer_prompt(self):
        client = httpx.Client(timeout=120.0)
        r = client.post(
            "http://localhost:11434/api/generate",
            json={
                "model": "smollm:135m",
                "prompt": "Explain what is a neural network in one sentence.",
                "stream": False
            }
        )
        assert r.status_code == 200
        data = r.json()
        assert len(data["response"]) > 10
        client.close()


class TestGPUDetection:
    def test_nvidia_smi_available(self):
        import subprocess
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
            capture_output=True,
            text=True
        )
        assert result.returncode == 0

    def test_gpu_memory_detected(self):
        import subprocess
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True
        )
        assert result.returncode == 0
        memory_mb = int(result.stdout.strip())
        assert memory_mb > 0

    def test_ollama_gpu_usage(self):
        client = httpx.Client(timeout=60.0)

        import subprocess
        subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
            capture_output=True
        )

        r = client.post(
            "http://localhost:11434/api/generate",
            json={"model": "smollm:135m", "prompt": "Test", "stream": False}
        )
        assert r.status_code == 200

        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
            capture_output=True,
            text=True
        )
        memory_used = int(result.stdout.strip())
        assert memory_used > 0, "Ollama should use GPU memory"

        client.close()


class TestPerformance:
    def test_inference_latency(self):
        client = httpx.Client(timeout=60.0)

        start = time.time()
        r = client.post(
            "http://localhost:11434/api/generate",
            json={"model": "smollm2:135m", "prompt": "What is 2+2?", "stream": False}
        )
        latency = time.time() - start

        assert r.status_code == 200
        assert latency < 30, f"Latency too high: {latency:.2f}s"

        client.close()

    def test_embedding_latency(self):
        client = httpx.Client(timeout=60.0)

        start = time.time()
        r = client.post(
            "http://localhost:11434/api/embeddings",
            json={"model": "nomic-embed-text:latest", "prompt": "test document"}
        )
        latency = time.time() - start

        assert r.status_code == 200
        assert latency < 5, f"Embedding latency too high: {latency:.2f}s"

        client.close()


def run_ollama_health_check():
    print("=" * 60)
    print("OLLAMA HEALTH CHECK")
    print("=" * 60)

    import subprocess

    print("\n1. Checking nvidia-smi...")
    result = subprocess.run(
        ["nvidia-smi", "--query-gpu=name,memory.total,driver_version", "--format=csv"],
        capture_output=True,
        text=True
    )
    if result.returncode == 0:
        print(f"   GPU: {result.stdout.strip()}")
    else:
        print("   ERROR: nvidia-smi not available")

    print("\n2. Checking Ollama models...")
    client = httpx.Client(timeout=10.0)
    try:
        r = client.get("http://localhost:11434/api/tags")
        models = r.json().get("models", [])
        for m in models:
            print(f"   - {m['name']}")
    except Exception as e:
        print(f"   ERROR: {e}")
    finally:
        client.close()

    print("\n3. Testing inference...")
    client = httpx.Client(timeout=60.0)
    try:
        start = time.time()
        r = client.post(
            "http://localhost:11434/api/generate",
            json={"model": "smollm2:135m", "prompt": "Hello", "stream": False}
        )
        elapsed = time.time() - start
        print(f"   Status: OK ({elapsed:.2f}s)")
    except Exception as e:
        print(f"   ERROR: {e}")
    finally:
        client.close()

    print("\n" + "=" * 60)


if __name__ == "__main__":
    run_ollama_health_check()