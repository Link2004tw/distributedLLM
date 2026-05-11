from typing import List


class Retriever:
    def __init__(self):
        self._sample_docs = [
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

    def set_base_url(self, url: str):
        pass

    def retrieve(self, query: str, top_k: int = 3) -> List[str]:
        import random
        k = min(top_k, len(self._sample_docs))
        return random.sample(self._sample_docs, k)

    def retrieve_with_scores(self, query: str, top_k: int = 3) -> List[tuple]:
        import random
        k = min(top_k, len(self._sample_docs))
        docs = random.sample(self._sample_docs, k)
        scores = [round(0.95 - i * 0.1, 2) for i in range(k)]
        return list(zip(docs, scores))


retriever = Retriever()
