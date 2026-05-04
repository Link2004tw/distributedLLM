from rag.retriever import retriever
from llm.inference import InferenceEngine


def test_retriever_only():
    print("=" * 60)
    print("TEST 1: Retriever Only (No LLM)")
    print("=" * 60)

    queries = [
        "What do hamsters eat?",
        "Goldfish memory",
        "Rabbit teeth",
        "Parrot lifespan",
    ]

    for query in queries:
        print(f"\nQuery: {query}")
        results = retriever.retrieve_with_scores(query, top_k=2)
        for i, (doc, score) in enumerate(results, 1):
            print(f"  [{i}] Score: {score:.4f}")
            print(f"      {doc[:120]}...")


def test_full_rag():
    print("\n" + "=" * 60)
    print("TEST 2: Full RAG (Retriever + LLM)")
    print("=" * 60)

    llm = InferenceEngine()

    queries = [
        "What do hamsters eat?",
        "How long do goldfish live?",
        "Can rabbits eat carrots?",
    ]

    for query in queries:
        print(f"\nQuery: {query}")
        docs = retriever.retrieve(query, top_k=3)
        response = llm.generate_with_context(query, docs)
        print(f"Answer: {response}")
        print("-" * 40)


if __name__ == "__main__":
    test_retriever_only()
    test_full_rag()