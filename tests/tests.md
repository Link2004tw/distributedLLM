# Test Suite

## Overview
100 total tests across 6 modules.

---

## test_load_balancer.py
**Mark:** `health`, `load`

### TestLoadBalancerHealth
| Test | Description |
|------|-------------|
| `test_health_endpoint` | GET /health returns 200 with healthy status |
| `test_workers_endpoint` | GET /workers returns workers list and strategy |
| `test_stats_endpoint` | GET /stats returns worker metrics |
| `test_strategy_endpoint_get` | GET /strategy returns current routing strategy |

### TestLoadBalancerRouting
| Test | Description |
|------|-------------|
| `test_round_robin_strategy` | Round robin routing works correctly |
| `test_least_connections_strategy` | Least connections routing works |
| `test_hybrid_strategy` | Hybrid routing strategy works |
| `test_gpu_aware_strategy` | GPU-aware routing strategy works |
| `test_capacity_aware_strategy` | Capacity-aware routing considers queue availability |
| `test_invalid_strategy_rejected` | Invalid strategy returns 400 |

### TestConcurrentRequestHandling
**Mark:** `load`

| Test | Description |
|------|-------------|
| `test_capacity_aware_strategy` | Capacity-aware routing considers queue availability |
| `test_worker_reports_queue_available` | Worker reports queue_available in health check |

### TestLoadBalancerQuery
| Test | Description |
|------|-------------|
| `test_query_returns_answer` | Query endpoint returns answer and latency |
| `test_query_uses_worker_gpu_stats` | Worker GPU stats are reported |

### TestLoadBalancerWorkerManagement
| Test | Description |
|------|-------------|
| `test_mark_worker_unhealthy` | POST /worker/unhealthy marks worker down |
| `test_mark_worker_healthy` | POST /worker/healthy marks worker up |
| `test_add_worker` | POST /workers/add adds new worker |
| `test_remove_worker` | POST /workers/remove removes worker |

### TestAutomaticTaskReassignment
**Mark:** `fault_tolerance`

| Test | Description |
|------|-------------|
| `test_stats_endpoint_accessible` | Stats endpoint is accessible |
| `test_pending_requests_metric_present_or_missing` | Stats include request metrics |
| `test_query_succeeds_with_single_worker` | Query works with single healthy worker |
| `test_worker_marked_unhealthy_endpoint_exists` | Unhealthy worker endpoint exists |

---

## test_gpu_worker.py
**Mark:** `health`, `load`, `gpu`

### TestGPUWorkerHealth
| Test | Description |
|------|-------------|
| `test_health_endpoint` | GET /health returns worker health status |
| `test_ready_endpoint` | GET /ready checks worker readiness |
| `test_worker_id_endpoint` | GET /worker-id returns worker ID |
| `test_capabilities_endpoint` | GET /capabilities returns worker capabilities |

### TestGPUWorkerQuery
| Test | Description |
|------|-------------|
| `test_query_returns_answer` | POST /query returns LLM answer |
| `test_query_includes_latency` | Response includes latency_ms |
| `test_query_with_sources` | Response includes source documents |

### TestGPUWorkerBatchQuery
| Test | Description |
|------|-------------|
| `test_batch_query_returns_results` | Batch queries return all results |
| `test_batch_query_size_reporting` | Batch size is reported in response |
| `test_batch_optimized_returns_all` | Optimized batch processes all queries |
| `test_batch_cache_hit` | Batch queries use response cache |

### TestGPUMetrics
| Test | Description |
|------|-------------|
| `test_gpu_stats_endpoint` | GET /gpu-stats returns GPU metrics |
| `test_gpu_stats_has_utilization` | GPU utilization is reported |
| `test_gpu_stats_has_memory` | GPU memory is reported |

### TestGPUDetection
| Test | Description |
|------|-------------|
| `test_nvidia_smi_available` | nvidia-smi is available |
| `test_gpu_memory_detected` | GPU memory is detected |
| `test_ollama_gpu_usage` | Ollama GPU usage is shown |

### TestPerformance
| Test | Description |
|------|-------------|
| `test_inference_latency` | Inference latency is measured |
| `test_embedding_latency` | Embedding latency is measured |

---

## test_rag.py
**Mark:** `query`

### TestRetrieverInit
| Test | Description |
|------|-------------|
| `test_retriever_singleton_initialized` | Retriever singleton is initialized |
| `test_retriever_new_instance` | New retriever instance can be created |
| `test_retriever_set_base_url` | Base URL can be set on retriever |

### TestChromaDB
| Test | Description |
|------|-------------|
| `test_chroma_db_connection` | ChromaDB connects successfully |
| `test_chroma_db_has_documents` | ChromaDB contains documents |
| `test_chroma_db_collection_name` | Collection name is correct |

### TestRetrieval
| Test | Description |
|------|-------------|
| `test_retrieve_returns_list` | Retrieval returns a list |
| `test_retrieve_with_scores` | Retrieval includes relevance scores |
| `test_retrieve_empty_query` | Empty query returns empty list |
| `test_retrieve_top_k_respected` | top_k parameter is respected |
| `test_retrieve_relevance` | Retrieved docs are relevant to query |

### TestEmbedding
| Test | Description |
|------|-------------|
| `test_embed_query` | Query embedding works |
| `test_embed_query_stability` | Same query produces stable embeddings |
| `test_embed_query_different_for_different_text` | Different text produces different embeddings |

### TestSpecificQueries
| Test | Description |
|------|-------------|
| `test_dog_query_retrieval` | Dog-related query retrieves relevant docs |
| `test_cat_query_retrieval` | Cat-related query retrieves relevant docs |
| `test_hamster_query_retrieval` | Hamster-related query retrieves relevant docs |
| `test_no_match_query` | Non-matching query returns empty |

### TestCacheIntegration
| Test | Description |
|------|-------------|
| `test_embed_caching_in_worker` | Embedding caching works |
| `test_response_caching_in_worker` | Response caching works |

### TestEndToEndRAG
| Test | Description |
|------|-------------|
| `test_rag_pipeline_dog` | End-to-end RAG pipeline for dog query |
| `test_rag_pipeline_cat` | End-to-end RAG pipeline for cat query |
| `test_rag_context_in_answer` | Retrieved context appears in answer |

### TestRetrievalMetrics
| Test | Description |
|------|-------------|
| `test_retrieval_latency` | Retrieval latency is measured |
| `test_embedding_latency` | Embedding latency is measured |

### TestErrorHandling
| Test | Description |
|------|-------------|
| `test_invalid_top_k` | Invalid top_k is handled gracefully |
| `test_very_long_query` | Very long query is handled |

---

## test_ollama.py
**Mark:** `query`, `gpu`

### TestOllamaInit
| Test | Description |
|------|-------------|
| `test_inference_engine_initialized` | Inference engine initializes |
| `test_inference_engine_set_base_url` | Base URL can be set |

### TestOllamaGeneration
| Test | Description |
|------|-------------|
| `test_generate_simple_prompt` | Simple prompt generates response |
| `test_generate_with_context` | Context-enhanced generation works |
| `test_generate_with_longer_prompt` | Longer prompts work |

### TestOllamaEmbeddings
| Test | Description |
|------|-------------|
| `test_nomic_embed_model_available` | Nomic embed model is available |

### TestOllamaEndpoints
| Test | Description |
|------|-------------|
| `test_generate_endpoint` | /generate endpoint works |
| `test_embedding_endpoint` | /embedding endpoint works |
| `test_generate_with_longer_prompt` | Longer prompts work with API |

---

## test_critical_fixes.py
| Test | Description |
|------|-------------|
| `test_no_executor_timeout` | No executor timeout issue |
| `test_duplicate_imports` | No duplicate imports |
| `test_worker_registration_on_startup` | Worker registers on startup |
| `test_httpx_client_cleanup` | httpx client cleans up properly |

---

## Running Tests

```bash
# All tests
pytest tests/

# By mark
pytest tests/ -m health
pytest tests/ -m load
pytest tests/ -m gpu
pytest tests/ -m query
pytest tests/ -m fault_tolerance

# Specific file
pytest tests/test_load_balancer.py

# Specific class
pytest tests/test_load_balancer.py::TestAutomaticTaskReassignment
```

---

## Last Updated
2026-05-11
