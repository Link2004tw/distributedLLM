import os
import httpx
import asyncio
from typing import List, Optional, Dict, Any
from collections import OrderedDict
import time


LLM_MODEL = "smollm2:135m"
EMBEDDING_MODEL = "nomic-embed-text:latest"
OLLAMA_URL = os.environ.get("OLLAMA_URL", "http://localhost:11434")
CACHE_SIZE = 500


class OllamaClient:
    def __init__(
        self,
        base_url: str = OLLAMA_URL,
        max_connections: int = 20,
        max_keepalive: int = 10,
        timeout: float = 120.0
    ):
        self.base_url = base_url
        self._client: Optional[httpx.AsyncClient] = None
        self._limits = httpx.Limits(
            max_connections=max_connections,
            max_keepalive_connections=max_keepalive
        )
        self._timeout = timeout
        self._lock = asyncio.Lock()

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()

    async def connect(self):
        if self._client is None:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self._timeout,
                limits=self._limits
            )

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None

    async def generate(
        self,
        prompt: str,
        model: str = LLM_MODEL,
        stream: bool = False,
        options: Optional[Dict[str, Any]] = None
    ) -> Dict[str, Any]:
        if self._client is None:
            await self.connect()

        payload = {
            "model": model,
            "prompt": prompt,
            "stream": stream
        }
        if options:
            payload["options"] = options

        response = await self._client.post("/api/generate", json=payload)
        response.raise_for_status()
        return response.json()

    async def batch_generate(
        self,
        prompts: List[str],
        model: str = LLM_MODEL,
        options: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        if self._client is None:
            await self.connect()

        tasks = []
        for prompt in prompts:
            payload = {
                "model": model,
                "prompt": prompt,
                "stream": False
            }
            if options:
                payload["options"] = options
            tasks.append(self._client.post("/api/generate", json=payload))

        responses = await asyncio.gather(*tasks, return_exceptions=True)
        results = []
        for resp in responses:
            if isinstance(resp, Exception):
                results.append({"error": str(resp), "response": ""})
            else:
                results.append(resp.json())
        return results

    async def embed(self, text: str, model: str = EMBEDDING_MODEL) -> List[float]:
        if self._client is None:
            await self.connect()

        response = await self._client.post(
            "/api/embeddings",
            json={"model": model, "prompt": text}
        )
        response.raise_for_status()
        data = response.json()
        return data.get("embedding", [])

    async def batch_embed(
        self,
        texts: List[str],
        model: str = EMBEDDING_MODEL
    ) -> List[List[float]]:
        tasks = [self.embed(text, model) for text in texts]
        return await asyncio.gather(*tasks, return_exceptions=True)


class BatchProcessor:
    def __init__(
        self,
        ollama_client: OllamaClient,
        batch_size: int = 10,
        batch_timeout_ms: int = 50
    ):
        self.client = ollama_client
        self.batch_size = batch_size
        self.batch_timeout = batch_timeout_ms / 1000.0
        self.embedding_queue: List[Dict[str, Any]] = []
        self.inference_queue: List[Dict[str, Any]] = []
        self._embed_task: Optional[asyncio.Task] = None
        self._inference_task: Optional[asyncio.Task] = None
        self._running = False

    def start(self):
        self._running = True
        self._embed_task = asyncio.create_task(self._process_embedding_queue())
        self._inference_task = asyncio.create_task(self._process_inference_queue())

    async def stop(self):
        self._running = False
        if self._embed_task:
            self._embed_task.cancel()
        if self._inference_task:
            self._inference_task.cancel()

    async def _process_embedding_queue(self):
        while self._running:
            await asyncio.sleep(self.batch_timeout)
            if self.embedding_queue:
                batch = self.embedding_queue[:self.batch_size]
                self.embedding_queue = self.embedding_queue[self.batch_size:]
                texts = [item["text"] for item in batch]
                try:
                    embeddings = await self.client.batch_embed(texts)
                    for item, embedding in zip(batch, embeddings):
                        if not isinstance(embedding, Exception):
                            item["future"].set_result(embedding)
                        else:
                            item["future"].set_exception(embedding)
                except Exception as e:
                    for item in batch:
                        item["future"].set_exception(e)

    async def _process_inference_queue(self):
        while self._running:
            await asyncio.sleep(self.batch_timeout)
            if self.inference_queue:
                batch = self.inference_queue[:self.batch_size]
                self.inference_queue = self.inference_queue[self.batch_size:]
                prompts = [item["prompt"] for item in batch]
                try:
                    results = await self.client.batch_generate(prompts)
                    for item, result in zip(batch, results):
                        if "error" not in result:
                            item["future"].set_result(result.get("response", ""))
                        else:
                            item["future"].set_exception(Exception(result["error"]))
                except Exception as e:
                    for item in batch:
                        item["future"].set_exception(e)

    async def queue_embedding(self, text: str) -> List[float]:
        future = asyncio.Future()
        self.embedding_queue.append({"text": text, "future": future})
        return await future

    async def queue_inference(self, prompt: str) -> str:
        future = asyncio.Future()
        self.inference_queue.append({"prompt": prompt, "future": future})
        return await future


class LRU_Cache:
    def __init__(self, max_size: int = CACHE_SIZE):
        self.cache: OrderedDict = OrderedDict()
        self.max_size = max_size

    def get(self, key: str) -> Optional[Any]:
        if key in self.cache:
            self.cache.move_to_end(key)
            return self.cache[key]
        return None

    def set(self, key: str, value: Any):
        if key in self.cache:
            self.cache.move_to_end(key)
        else:
            if len(self.cache) >= self.max_size:
                self.cache.popitem(last=False)
        self.cache[key] = value

    def __len__(self):
        return len(self.cache)

    def clear(self):
        self.cache.clear()


class GPUInferenceEngine:
    def __init__(
        self,
        ollama_url: str = OLLAMA_URL,
        batch_size: int = 10,
        cache_size: int = CACHE_SIZE
    ):
        self.ollama_url = ollama_url
        self.batch_size = batch_size
        self.client = OllamaClient(base_url=ollama_url)
        self.batch_processor = BatchProcessor(self.client, batch_size=batch_size)
        self.response_cache = LRU_Cache(max_size=cache_size)
        self.embed_cache = LRU_Cache(max_size=cache_size)

    async def initialize(self):
        await self.client.connect()
        self.batch_processor.start()

    async def shutdown(self):
        await self.batch_processor.stop()
        await self.client.close()

    def _make_cache_key(self, query: str, top_k: int) -> str:
        normalized = query.lower().strip()[:200]
        return f"{hash(normalized)}:{top_k}"

    def _make_embed_key(self, query: str) -> str:
        return hash(query.lower().strip()[:200])

    async def generate(
        self,
        query: str,
        context_docs: List[str],
        use_cache: bool = True
    ) -> str:
        cache_key = self._make_cache_key(query, 3)
        if use_cache:
            cached = self.response_cache.get(cache_key)
            if cached:
                return cached

        context = "\n\n".join(context_docs)
        prompt = f"""Context information:
{context}

Question: {query}

Answer based on the context above:"""

        result = await self.client.generate(prompt=prompt, stream=False)

        if "response" in result:
            self.response_cache.set(cache_key, result["response"])
            return result["response"]
        return ""

    async def embed(self, text: str, use_cache: bool = True) -> List[float]:
        embed_key = self._make_embed_key(text)
        if use_cache:
            cached = self.embed_cache.get(embed_key)
            if cached is not None:
                return cached

        embedding = await self.client.embed(text)
        self.embed_cache.set(embed_key, embedding)
        return embedding

    async def batch_generate(
        self,
        queries: List[Dict[str, Any]],
        use_cache: bool = True
    ) -> List[Dict[str, Any]]:
        results = []
        uncached = []

        for i, item in enumerate(queries):
            query = item["query"]
            context_docs = item.get("context", [])
            cache_key = self._make_cache_key(query, 3)

            if use_cache:
                cached = self.response_cache.get(cache_key)
                if cached:
                    results.append({"query": query, "answer": cached, "cache_hit": True})
                    continue

            uncached.append({
                "index": i,
                "query": query,
                "context_docs": context_docs,
                "cache_key": cache_key
            })

        if uncached:
            prompts = []
            for item in uncached:
                context = "\n\n".join(item["context_docs"])
                prompt = f"""Context information:
{context}

Question: {item['query']}

Answer based on the context above:"""
                prompts.append(prompt)

            batch_results = await self.client.batch_generate(prompts)

            for item, result in zip(uncached, batch_results):
                if "error" not in result:
                    answer = result.get("response", "")
                    self.response_cache.set(item["cache_key"], answer)
                    results.append({
                        "query": item["query"],
                        "answer": answer,
                        "cache_hit": False
                    })
                else:
                    results.append({
                        "query": item["query"],
                        "answer": f"Error: {result['error']}",
                        "cache_hit": False,
                        "error": True
                    })

        return results


ollama_client = OllamaClient(base_url=OLLAMA_URL)
inference_engine = GPUInferenceEngine(ollama_url=OLLAMA_URL)