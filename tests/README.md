# Test Suite

Test files in `tests/` folder:

- `conftest.py` - Shared pytest fixtures
- `test_gpu_worker.py` - GPU worker endpoint tests
- `test_load_balancer.py` - Load balancer tests
- `test_ollama.py` - Ollama integration tests
- `run_tests.bat` - Windows test runner

## Run Tests

```bash
# All tests
pytest tests/ -v

# By category
pytest tests/ -v -m health
pytest tests/ -v -m load

# Quick test
python tests/test_gpu_worker.py
```

## Prerequisites

Start services first:
```bash
ollama serve
python -m uvicorn workers.gpu_worker:app --port 8001
python -m uvicorn lb.load_balancer:app --port 8000
```