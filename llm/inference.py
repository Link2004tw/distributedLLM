import os
import asyncio
import httpx
from typing import List, Optional


LLM_MODEL = os.environ.get("LLM_MODEL", "smollm2:135m")
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
OLLAMA_NUM_GPU = os.environ.get("OLLAMA_NUM_GPU", "")
OLLAMA_CONTEXT_LENGTH = os.environ.get("OLLAMA_CONTEXT_LENGTH", "")
OLLAMA_BATCH_SIZE = os.environ.get("OLLAMA_BATCH_SIZE", "")


class InferenceEngine:
    def __init__(self, model: str = LLM_MODEL):
        self.model = model
        self._client: Optional[httpx.AsyncClient] = None
        self._semaphore: Optional[asyncio.Semaphore] = None

    async def init_client(self):
        limits = httpx.Limits(max_connections=500, max_keepalive_connections=250)
        self._client = httpx.AsyncClient(
            base_url=OLLAMA_BASE_URL,
            timeout=httpx.Timeout(3600.0, connect=30.0),
            limits=limits
        )
        self._semaphore = asyncio.Semaphore(20)

    async def close(self):
        if self._client:
            await self._client.aclose()

    def _build_generate_payload(self, prompt: str) -> dict:
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
        }
        if OLLAMA_NUM_GPU:
            payload["options"] = {"num_gpu": int(OLLAMA_NUM_GPU)}
        if OLLAMA_CONTEXT_LENGTH:
            if "options" not in payload:
                payload["options"] = {}
            payload["options"]["num_ctx"] = int(OLLAMA_CONTEXT_LENGTH)
        if OLLAMA_BATCH_SIZE:
            if "options" not in payload:
                payload["options"] = {}
            payload["options"]["num_batch"] = int(OLLAMA_BATCH_SIZE)
        return payload

    async def generate(self, prompt: str) -> str:
        if not self._client:
            raise RuntimeError("Client not initialized. Call init_client() first.")
        async with self._semaphore:
            payload = self._build_generate_payload(prompt)
            resp = await self._client.post("/api/generate", json=payload)
            resp.raise_for_status()
            data = resp.json()
            return data.get("response", "")

    async def generate_with_context(self, query: str, context_docs: List[str]) -> str:
        context = "\n\n".join(context_docs)
        prompt = f"""Context information:
{context}

Question: {query}

Answer based on the context above:"""
        return await self.generate(prompt)

    async def generate_batch(self, queries: List[str], contexts: List[List[str]]) -> List[str]:
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

        tasks = [self.generate(p) for p in prompts]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        output = []
        for r in results:
            if isinstance(r, Exception):
                print(f"Batch generate error: {r}")
                output.append("Service temporarily unavailable. Please retry.")
            else:
                output.append(r)
        return output


inference_engine = InferenceEngine()
