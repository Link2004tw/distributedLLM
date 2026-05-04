# Project Task List

## Status Legend
- [x] Completed
- [ ] Pending
- [ ] In Progress

---

## Tasks

| # | Task | Status |
|---|------|--------|
| 1 | Install Python dependencies (requirements.txt) | [x] Completed |
| 2 | Pull Ollama models (smollm2, bge-m3) | [x] Completed |
| 3 | Create sample documents (cat_facts.txt, dog_facts.txt) | [x] Completed |
| 4 | Ingest documents into ChromaDB | [x] Completed |
| 5 | Fix langchain import issues | [x] Completed |
| 6 | Update retriever to use Ollama embeddings | [x] Completed |
| 7 | Start Master Node (port 9000) | [ ] Pending |
| 8 | Start Worker Nodes (ports 8001-8004) | [ ] Pending |
| 9 | Start Load Balancer (port 8000) | [ ] Pending |
| 10 | Run load test (client/load_generator.py) | [ ] Pending |
| 11 | Test the system end-to-end | [ ] Pending |

---

## Implementation Order (Recommended)

1. Ingest documents into ChromaDB
2. Start Master Node
3. Start Worker Nodes
4. Start Load Balancer
5. Run load test
6. Test the system end-to-end