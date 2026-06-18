# Code Refactoring Tasks

> Generated from code review — prioritized by impact.

---

## P0 — Critical

- [ ] **Fix silent `except Exception: pass` (11 locations)**
  - `master/monitor.py:61,76-77,87-88`
  - `worker/worker.py:79-80,365-366`
  - `lb/load_balancer.py:176-177,216-217,332-333,383-384`
  - `dashboard/app.py:45-47`
  - Replace bare `pass` with `logger.warning(...)` or `logger.debug(...)`.

- [ ] **Add locks to async caches in worker.py**
  - `embed_cache` and `response_cache` are mutated across coroutines without locks.
  - Use `asyncio.Lock` or switch to `cachetools.TTLCache`.

- [ ] **Pin dependency versions in requirements.txt**
  - 7/10 packages have no version constraints — `pip install` is non-deterministic.
  - Add minimum major version pins for all packages.

---

## P1 — High

- [ ] **Fix `active_connections` cleanup in load_balancer.py**
  - `lb/load_balancer.py:442` — decrement happens in both `try` and `except` blocks; should be in `finally`.

- [ ] **Add Pydantic field validation**
  - `workers/worker.py:44-47` — `QueryRequest.query` needs `max_length`, `top_k` needs `ge`/`le`.
  - `lb/load_balancer.py` — add constraints to request models.

- [ ] **Fix no-op test assertion**
  - `tests/test_load_balancer.py:199` — `assert ... or True` always passes.

- [ ] **Extract `start_component()` to `common/process_launcher.py`**
  - Duplicated in `main.py:24-38`, `benchmark.py:69-82`, `quick_setup.py:24-35`.

- [ ] **Replace `print()` with `logging` (15+ occurrences)**
  - Add `logging.getLogger(__name__)` and replace all `print()` statements.

- [ ] **Create reusable `LRUCache` class**
  - 5x manual LRU eviction pattern in `workers/worker.py:132-348`.
  - Extract into a `LRUCache` class using `OrderedDict`.

- [ ] **Return cache hits before semaphore acquisition**
  - `workers/worker.py:188-196` — cache-hit requests wait unnecessarily for `request_semaphore`.

- [ ] **Remove dead batch-processing code**
  - `process_batch_queries` and `process_batch_single` may be unused; verify and remove.

---

## P2 — Medium

- [ ] **Extract routing strategies to `common/routing.py`**
  - Identical logic in `master/monitor.py:151-209` and `lb/load_balancer.py:226-300`.
  - Define a protocol interface for worker state.

- [ ] **Consolidate batch processing methods**
  - `workers/worker.py` has three paths: `process_batch_queries`, `process_batch_single`, `process_batch_optimized`.
  - Merge into one.

- [ ] **Add unit tests for pure functions**
  - Routing selection, cache eviction, payload construction, percentile calculations.
  - Use `pytest` + `pytest-asyncio` + `unittest.mock`.

- [ ] **Centralize port configuration**
  - Ports hardcoded in 8+ locations across all modules.
  - Create `common/config.py` with `DEFAULT_PORTS`.

- [ ] **Fix latency rolling window in worker.py:388-392**
  - Use `deque(maxlen=100)` with running sum instead of `list` + `sum()` on every request.

- [ ] **Add `.gitignore` for generated artifacts**
  - Cover `chroma_db/`, `__pycache__/`, result JSONs, `*.pyc`.

- [ ] **Fix master scheduling bottleneck**
  - `lb/load_balancer.py:196-223` — every request hits `/schedule` on master.
  - Make master scheduling optional (default to local-only routing).

---

## P3 — Low

- [ ] **Split large files**
  - `workers/worker.py` (547 lines) → `routes.py`, `processing.py`, `cache.py`, `gpu.py`
  - `lb/load_balancer.py` (658 lines) → `routing.py`, `routes.py`, `models.py`
  - `benchmark.py` (693 lines) → `benchmark_runner.py`, `reporting.py`

- [ ] **Add docstrings to public functions and API endpoints**
  - All endpoint handlers, selection strategies, cache methods, benchmark flows.

- [ ] **Unify `WorkerInfo` and `WorkerState`**
  - `common/models.py:26-33` vs `lb/load_balancer.py:33-47` — same concept, different types.

- [ ] **Convert `test_failure_simulation.py` to proper pytest**
  - Uses `print()` and manual orchestration — doesn't run via `pytest`.

- [ ] **Add GPU name detection**
  - `workers/worker.py:483` — hardcoded `"NVIDIA GeForce RTX 3060 Laptop"`; detect dynamically.

- [ ] **Add CORS origin restrictions note**
  - `dashboard/app.py:12-16` — `allow_origins=["*"]` is permissive; add a config option.

- [ ] **Use `finally` for pending request cleanup**
  - `lb/load_balancer.py:88-106` — JSON file persistence is fragile under concurrent writes.

- [ ] **Replace `LoadBalancer` class vs module-level globals mixed paradigm**
  - `lb/load_balancer.py:595-653` — class wraps globals but doesn't own them.
  - Either use the class properly or remove it in favor of module-level functions.

- [ ] **Add health check metrics to master**
  - `master/monitor.py:46` — no metrics about missed heartbeats.
  - Add consecutive-failure counter and recovery-time tracking.

---

## Legend

| Priority | Meaning |
|----------|---------|
| **P0** | Bug or risk that can cause incorrect behavior in production |
| **P1** | Structural issue affecting maintainability or correctness |
| **P2** | Valuable improvement, moderate effort |
| **P3** | Nice-to-have refactor, larger effort |
