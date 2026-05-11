from typing import List

SAMPLE_DOCS = [
    "Distributed computing is a model where components are located on different networked computers.",
    "Load balancing distributes workloads across multiple resources to optimize throughput and prevent overload.",
    "RAG (Retrieval-Augmented Generation) combines retrieval systems with generative models for grounded responses.",
    "Fault tolerance is the ability of a system to continue operating despite failures in some components.",
    "A master node monitors worker health and coordinates task distribution across the cluster.",
    "Round robin routing distributes requests sequentially across available servers in a fixed order.",
    "Least connections routing sends requests to the server with the fewest active connections.",
    "Worker failure detection uses periodic heartbeat signals between master and worker nodes.",
    "Horizontal scaling improves throughput by adding more worker nodes to the cluster.",
    "Embedding models convert text into numerical vectors for semantic similarity search.",
]


class Retriever:
    def __init__(self, base_url: str = None):
        pass

    def set_base_url(self, url: str):
        pass

    def retrieve(self, query: str, top_k: int = 3) -> List[str]:
        import random
        k = min(top_k, len(SAMPLE_DOCS))
        return random.sample(SAMPLE_DOCS, k)

    def retrieve_with_scores(self, query: str, top_k: int = 3) -> List[tuple]:
        import random
        k = min(top_k, len(SAMPLE_DOCS))
        docs = random.sample(SAMPLE_DOCS, k)
        scores = [round(0.95 - i * 0.1, 2) for i in range(k)]
        return list(zip(docs, scores))

    def retrieve_batch(self, queries: List[str], top_k: int = 3) -> List[List[str]]:
        import random
        return [random.sample(SAMPLE_DOCS, min(top_k, len(SAMPLE_DOCS))) for _ in queries]

    def get_count(self) -> int:
        return len(SAMPLE_DOCS)


retriever = Retriever()
