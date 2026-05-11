import time
from rag.retriever import retriever
from llm.inference import inference_engine

class GPUWorker:
    def __init__(self, worker_id: str):
        self.id = worker_id

    def process(self, query: str, request_id: str):
        start = time.time()
        print(f"[Worker {self.id}] Processing request {request_id}")
        
        try:
            docs = retriever.retrieve(query, top_k=3)
            answer = inference_engine.generate_with_context(query, docs)
            status = "success"
        except Exception as e:
            print(f"[Worker {self.id}] Pipeline failed: {e}")
            docs = []
            answer = "Fallback answer: The real RAG/Ollama pipeline failed or is unavailable."
            status = "fallback"

        latency = (time.time() - start) * 1000
        
        return {
            "request_id": request_id,
            "worker_id": self.id,
            "answer": answer,
            "sources": docs,
            "latency_ms": latency,
            "status": status
        }