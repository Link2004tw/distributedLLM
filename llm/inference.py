import os
import httpx
from typing import List, Optional
from langchain_ollama import OllamaLLM


LLM_MODEL = os.environ.get("LLM_MODEL", "smollm2:135m")
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_NUM_GPU = os.environ.get("OLLAMA_NUM_GPU", "")
OLLAMA_CONTEXT_LENGTH = os.environ.get("OLLAMA_CONTEXT_LENGTH", "")
OLLAMA_BATCH_SIZE = os.environ.get("OLLAMA_BATCH_SIZE", "")


class InferenceEngine:
    def __init__(self, model: str = LLM_MODEL):
        kwargs = {"model": model}
        if OLLAMA_NUM_GPU:
            kwargs["num_gpu"] = int(OLLAMA_NUM_GPU)
        if OLLAMA_CONTEXT_LENGTH:
            kwargs["num_ctx"] = int(OLLAMA_CONTEXT_LENGTH)
        if OLLAMA_BATCH_SIZE:
            kwargs["num_batch"] = int(OLLAMA_BATCH_SIZE)
        self.llm = OllamaLLM(**kwargs)

    def set_base_url(self, url: str):
        from langchain_ollama import OllamaLLM
        kwargs = {"model": self.llm.model, "base_url": url}
        self.llm = OllamaLLM(**kwargs)

    def generate(self, prompt: str, streaming: bool = False):
        if streaming:
            return self.llm.stream(prompt)
        return self.llm.invoke(prompt)

    def generate_with_context(self, query: str, context_docs: List[str]) -> str:
        context = "\n\n".join(context_docs)
        prompt = f"""Context information:
{context}

Question: {query}

Answer based on the context above:"""
        return self.generate(prompt)

    def stream_with_context(self, query: str, context_docs: List[str]):
        context = "\n\n".join(context_docs)
        prompt = f"""Context information:
{context}

Question: {query}

Answer based on the context above:"""
        return self.generate(prompt, streaming=True)

    def generate_batch(self, queries: List[str], contexts: List[List[str]]) -> List[str]:
        prompts = []
        for query, docs in zip(queries, contexts):
            if docs:
                context = "\n\n".join(docs)
                prompt = f"""Context information:
{context}

Question: {query}

Answer based on the context above:"""
            else:
                prompt = query
            prompts.append(prompt)

        try:
            results = self.llm.batch(prompts)
            return [str(r) for r in results]
        except Exception as e:
            print(f"Batch generation error: {e}")
            return ["Service temporarily unavailable. Please retry." for _ in queries]


inference_engine = InferenceEngine()