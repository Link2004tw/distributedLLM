import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
os.environ["OLLAMA_BASE_URL"] = "http://localhost:11434"
os.environ["CHROMA_DB_PATH"] = "./chroma_db"

import pytest
from rag.retriever import Retriever, retriever


class TestRetrieverInit:
    def test_retriever_singleton_initialized(self):
        assert retriever is not None
        assert retriever.embeddings is not None
        assert retriever.db is not None

    def test_retriever_new_instance(self):
        r = Retriever()
        assert r.embeddings is not None
        assert r.db is not None

    def test_retriever_set_base_url(self):
        r = Retriever()
        r.set_base_url("http://localhost:11434")
        assert r.base_url == "http://localhost:11434"


class TestChromaDB:
    def test_chroma_db_connection(self):
        r = Retriever()
        count = r.get_count()
        assert count >= 0, "ChromaDB should be accessible"

    def test_chroma_db_has_documents(self):
        count = retriever.get_count()
        assert count > 0, f"ChromaDB should have documents, found {count}"

    def test_chroma_db_collection_name(self):
        r = Retriever()
        assert r.db._collection.name == "documents"


class TestRetrieval:
    def test_retrieve_returns_list(self):
        docs = retriever.retrieve("dogs", top_k=3)
        assert isinstance(docs, list)
        assert len(docs) <= 3

    def test_retrieve_with_scores(self):
        results = retriever.retrieve_with_scores("cat", top_k=2)
        assert isinstance(results, list)
        assert len(results) <= 2
        for doc, score in results:
            assert isinstance(doc, str)
            assert isinstance(score, float)

    def test_retrieve_empty_query(self):
        docs = retriever.retrieve("", top_k=1)
        assert isinstance(docs, list)

    def test_retrieve_top_k_respected(self):
        for k in [1, 3, 5]:
            docs = retriever.retrieve("animal", top_k=k)
            assert len(docs) <= k

    def test_retrieve_relevance(self):
        dog_docs = retriever.retrieve("dog facts", top_k=5)
        cat_docs = retriever.retrieve("cat facts", top_k=5)
        assert len(dog_docs) > 0 or len(cat_docs) > 0


class TestEmbedding:
    def test_embed_query(self):
        embedding = retriever.embeddings.embed_query("test query")
        assert isinstance(embedding, list)
        assert len(embedding) > 0
        assert all(isinstance(x, float) for x in embedding)

    def test_embed_query_stability(self):
        emb1 = retriever.embeddings.embed_query("consistent query")
        emb2 = retriever.embeddings.embed_query("consistent query")
        assert emb1 == emb2

    def test_embed_query_different_for_different_text(self):
        emb1 = retriever.embeddings.embed_query("dog")
        emb2 = retriever.embeddings.embed_query("cat")
        assert emb1 != emb2


class TestSpecificQueries:
    def test_dog_query_retrieval(self):
        import httpx
        client = httpx.Client(timeout=60.0)
        response = client.post(
            "http://127.0.0.1:8001/query",
            json={"query": "What are interesting facts about dogs?", "top_k": 3}
        )
        assert response.status_code == 200
        data = response.json()
        assert "sources" in data
        assert len(data["sources"]) > 0
        client.close()

    def test_cat_query_retrieval(self):
        import httpx
        client = httpx.Client(timeout=60.0)
        response = client.post(
            "http://127.0.0.1:8001/query",
            json={"query": "Tell me about cats", "top_k": 3}
        )
        assert response.status_code == 200
        data = response.json()
        assert "sources" in data
        client.close()

    def test_hamster_query_retrieval(self):
        import httpx
        client = httpx.Client(timeout=60.0)
        response = client.post(
            "http://127.0.0.1:8001/query",
            json={"query": "hamster facts", "top_k": 2}
        )
        assert response.status_code == 200
        data = response.json()
        assert "sources" in data
        client.close()

    def test_no_match_query(self):
        import httpx
        client = httpx.Client(timeout=60.0)
        response = client.post(
            "http://127.0.0.1:8001/query",
            json={"query": "xyzzyplugh nothing matches this 12345", "top_k": 3}
        )
        assert response.status_code == 200
        client.close()


class TestCacheIntegration:
    def test_embed_caching_in_worker(self):
        import httpx
        client = httpx.Client(timeout=60.0)
        query = f"unique embed cache test {os.urandom(4).hex()}"
        r1 = client.post("http://127.0.0.1:8001/query", json={"query": query, "top_k": 2})
        assert r1.status_code == 200
        client.close()

    def test_response_caching_in_worker(self):
        import httpx
        client = httpx.Client(timeout=60.0)
        query = f"unique rag cache test {os.urandom(4).hex()}"

        r1 = client.post(
            "http://127.0.0.1:8001/query",
            json={"query": query, "top_k": 2}
        )
        assert r1.status_code == 200

        r2 = client.post(
            "http://127.0.0.1:8001/query",
            json={"query": query, "top_k": 2}
        )
        assert r2.status_code == 200
        hit2 = r2.json().get("cache_hit", False)
        assert hit2 == True, "Second identical query should be cached"
        client.close()


class TestEndToEndRAG:
    def test_rag_pipeline_dog(self):
        import httpx
        client = httpx.Client(timeout=120.0)
        response = client.post(
            "http://127.0.0.1:8001/query",
            json={"query": "How powerful is a dog's sense of smell?", "top_k": 3}
        )
        assert response.status_code == 200
        data = response.json()

        assert "answer" in data
        assert "sources" in data
        assert len(data["sources"]) > 0

        answer_lower = data["answer"].lower()
        sources_text = " ".join(data["sources"]).lower()

        smells_mentioned = "smell" in answer_lower or "smell" in sources_text
        assert smells_mentioned, "Answer should reference dog's sense of smell from retrieved docs"
        client.close()

    def test_rag_pipeline_cat(self):
        import httpx
        client = httpx.Client(timeout=120.0)
        response = client.post(
            "http://127.0.0.1:8001/query",
            json={"query": "Tell me cat facts", "top_k": 3}
        )
        assert response.status_code == 200
        data = response.json()

        assert "answer" in data
        assert len(data["sources"]) > 0
        client.close()

    def test_rag_context_in_answer(self):
        import httpx
        client = httpx.Client(timeout=120.0)
        response = client.post(
            "http://127.0.0.1:8001/query",
            json={"query": "What do dogs do when sleeping?", "top_k": 3}
        )
        assert response.status_code == 200
        data = response.json()

        sources_text = " ".join(data["sources"])
        assert "curl" in sources_text or "ball" in sources_text, "Retrieved docs should mention curling up"
        client.close()


class TestRetrievalMetrics:
    def test_retrieval_latency(self):
        import time
        start = time.time()
        docs = retriever.retrieve("dog", top_k=3)
        latency = (time.time() - start) * 1000

        assert latency < 5000, f"Retrieval should be fast, took {latency:.0f}ms"
        assert len(docs) > 0

    def test_embedding_latency(self):
        import time
        start = time.time()
        emb = retriever.embeddings.embed_query("test")
        latency = (time.time() - start) * 1000

        assert latency < 10000, f"Embedding should be fast, took {latency:.0f}ms"


class TestErrorHandling:
    def test_invalid_top_k(self):
        import pytest
        with pytest.raises(Exception):
            retriever.retrieve("test", top_k=0)

    def test_very_long_query(self):
        long_query = "a" * 1000
        docs = retriever.retrieve(long_query, top_k=3)
        assert isinstance(docs, list)


def run_quick_rag_test():
    print("=" * 60)
    print("RAG MODULE QUICK TEST")
    print("=" * 60)

    r = Retriever()

    print(f"\n1. ChromaDB Collection Count: {r.get_count()}")

    print("\n2. Testing retrieval for 'dog'...")
    docs = r.retrieve("dog", top_k=3)
    print(f"   Retrieved {len(docs)} documents")
    for i, doc in enumerate(docs[:2]):
        print(f"   Doc {i+1}: {doc[:80]}...")

    print("\n3. Testing embedding...")
    emb = r.embeddings.embed_query("test")
    print(f"   Embedding dimension: {len(emb)}")

    print("\n4. Testing retrieval with scores...")
    results = r.retrieve_with_scores("cat", top_k=2)
    for doc, score in results:
        print(f"   Score: {score:.4f} - {doc[:60]}...")

    print("\n" + "=" * 60)
    print("RAG quick test complete!")
    print("=" * 60)


if __name__ == "__main__":
    run_quick_rag_test()