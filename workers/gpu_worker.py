import time
from llm.inference import run_llm
from rag.retriever import retrieve_context

class GPUWorker:
    def __init__(self):
        self.id= id

    def process(self, request):
        start= time.time()
        print(f"[Worker {self.id}] Processing request {request.id}")
        #rag steps
        context=retrieve_context(request.query)
        #llm step
        result=run_llm(request.query, context)
        latency= time.time() - start
        
        return {
            id: request.id,
            result: result,
            latency: latency
        }