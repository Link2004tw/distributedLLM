from typing import List, Optional, Dict, Tuple
import os
from langchain_chroma import Chroma
from langchain_ollama import OllamaEmbeddings


EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "nomic-embed-text:latest")
CHROMA_DB_PATH = os.environ.get("CHROMA_DB_PATH", "./chroma_db")
COLLECTION_NAME = "documents"
CACHE_SIZE = int(os.environ.get("RETRIEVER_CACHE_SIZE", "128"))


class LRUCache:
    def __init__(self, capacity: int):
        self.capacity = capacity
        self._cache: Dict[str, Tuple[List[str], float]] = {}
        self._order: List[str] = []

    def get(self, key: str) -> Optional[List[str]]:
        if key in self._cache:
            self._order.remove(key)
            self._order.append(key)
            return self._cache[key][0]
        return None

    def put(self, key: str, value: List[str]):
        if key in self._cache:
            self._order.remove(key)
        elif len(self._cache) >= self.capacity:
            oldest = self._order.pop(0)
            del self._cache[oldest]
        self._cache[key] = (value, 0)
        self._order.append(key)


class Retriever:
    def __init__(self):
        self.embeddings = OllamaEmbeddings(
            model=EMBEDDING_MODEL,
        )
        self.db = Chroma(
            persist_directory=CHROMA_DB_PATH,
            embedding_function=self.embeddings,
            collection_name=COLLECTION_NAME,
        )
        self._cache = LRUCache(CACHE_SIZE)

    def retrieve(self, query: str, top_k: int = 3) -> List[str]:
        cached = self._cache.get(query)
        if cached is not None:
            return cached
        docs = self.db.similarity_search(query, k=top_k)
        result = [doc.page_content for doc in docs]
        self._cache.put(query, result)
        return result

    def retrieve_with_scores(self, query: str, top_k: int = 3) -> List[tuple]:
        docs_with_scores = self.db.similarity_search_with_score(query, k=top_k)
        return [(doc.page_content, score) for doc, score in docs_with_scores]


retriever = Retriever()