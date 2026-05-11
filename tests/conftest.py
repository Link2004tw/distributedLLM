import pytest
import os


@pytest.fixture(scope="session")
def lb_url():
    return os.environ.get("TEST_LB_URL", "http://127.0.0.1:8000")


@pytest.fixture(scope="session")
def master_url():
    return os.environ.get("TEST_MASTER_URL", "http://127.0.0.1:9000")


@pytest.fixture(scope="session")
def worker_url():
    return os.environ.get("TEST_WORKER_URL", "http://127.0.0.1:8001")


@pytest.fixture
def sample_query():
    return {"query": "What is distributed computing?", "top_k": 3, "user_id": "test-user"}


@pytest.fixture
def sample_queries():
    return [
        {"query": "What is AI?", "top_k": 3, "user_id": "user-1"},
        {"query": "Explain neural networks", "top_k": 3, "user_id": "user-2"},
        {"query": "How does load balancing work?", "top_k": 3, "user_id": "user-3"},
    ]


@pytest.fixture(scope="session")
def verify_services(lb_url):
    import httpx
    try:
        client = httpx.Client(timeout=5.0)
        r = client.get(f"{lb_url}/health")
        client.close()
        if r.status_code != 200:
            pytest.skip(f"Load balancer not available at {lb_url}")
    except Exception:
        pytest.skip(f"Services not running. Start LB, Master, and at least one Worker.")


def pytest_terminal_summary(terminalreporter, exitstatus, config):
    results = []
    for report in terminalreporter.stats.get('passed', []):
        results.append({"name": report.nodeid, "passed": True, "time": report.duration})
    for report in terminalreporter.stats.get('failed', []):
        results.append({"name": report.nodeid, "passed": False, "time": report.duration})

    if not results:
        return

    total = len(results)
    passed = sum(1 for r in results if r.get("passed", False))
    failed = total - passed
    accuracy = (passed / total * 100) if total > 0 else 0
    total_time = sum(r.get("time", 0) for r in results) * 1000
    avg_time = total_time / total if total > 0 else 0

    times = [(r.get("time", 0) or 0) * 1000 for r in results]
    total_time = sum(times)
    avg_time = total_time / total if total > 0 else 0
    max_time = max(times) if times else 0
    min_time = min(times) if times else 0

    terminalreporter.write_sep("=", "RAG TEST RESULTS SUMMARY")
    terminalreporter.write_line("")
    terminalreporter.write_line(f"  Total Tests:    {total}")
    terminalreporter.write_line(f"  Passed:         {passed}")
    terminalreporter.write_line(f"  Failed:         {failed}")
    terminalreporter.write_line(f"  Accuracy:       {accuracy:.2f}%")
    terminalreporter.write_line("")
    terminalreporter.write_line(f"  Total Time:     {total_time:.2f} ms")
    terminalreporter.write_line(f"  Average Time:   {avg_time:.2f} ms per test")
    terminalreporter.write_line(f"  Max Time:       {max_time:.2f} ms")
    terminalreporter.write_line(f"  Min Time:       {min_time:.2f} ms")
    terminalreporter.write_line("")
    terminalreporter.write_line("-" * 70)

    header = f"{'Test Name':<55} {'Status':<10} {'Time (ms)':<12}"
    terminalreporter.write_line(header)
    terminalreporter.write_line("-" * 70)

    for r in sorted(results, key=lambda x: x.get("time", 0), reverse=True):
        name = r.get("name", "").split("::")[-1].split("[")[0]
        t = (r.get("time", 0) or 0) * 1000
        status_str = "[PASS]" if r.get("passed") else "[FAIL]"
        terminalreporter.write_line(f"{name:<55} {status_str:<10} {t:>10.2f} ms")

    terminalreporter.write_line("=" * 70)