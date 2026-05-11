import os
import sys
from typing import List
from langchain_chroma import Chroma
from langchain_ollama import OllamaEmbeddings


EMBEDDING_MODEL = os.environ.get("EMBEDDING_MODEL", "nomic-embed-text:latest")
CHROMA_DB_PATH = os.environ.get("CHROMA_DB_PATH", "./chroma_db")
OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")
COLLECTION_NAME = "documents"


class Retriever:
    def __init__(self, base_url: str = None):
        self.base_url = base_url or OLLAMA_BASE_URL
        self.embeddings = OllamaEmbeddings(
            model=EMBEDDING_MODEL,
            base_url=self.base_url,
        )
        self.db = Chroma(
            persist_directory=CHROMA_DB_PATH,
            embedding_function=self.embeddings,
            collection_name=COLLECTION_NAME,
        )
        
        # Log initialization status
        doc_count = self.get_count()
        if doc_count == 0:
            print(f"[RAG] WARNING: No documents in ChromaDB. Run 'python ingest.py' to populate the database.", file=sys.stderr)
        else:
            print(f"[RAG] Retriever initialized with {doc_count} documents.", file=sys.stderr)

    def set_base_url(self, url: str):
        self.base_url = url
        self.embeddings = OllamaEmbeddings(
            model=self.embeddings.model,
            base_url=url,
        )
        self.db = Chroma(
            persist_directory=CHROMA_DB_PATH,
            embedding_function=self.embeddings,
            collection_name=COLLECTION_NAME,
        )

    def retrieve(self, query: str, top_k: int = 3) -> List[str]:
        docs = self.db.similarity_search(query, k=top_k)
        return [doc.page_content for doc in docs]

    def retrieve_with_scores(self, query: str, top_k: int = 3) -> List[tuple]:
        docs_with_scores = self.db.similarity_search_with_score(query, k=top_k)
        return [(doc.page_content, score) for doc, score in docs_with_scores]

    def retrieve_batch(self, queries: List[str], top_k: int = 3) -> List[List[str]]:
        if not queries:
            return []

        try:
            docs_batch = self.db.similarity_search_many(queries, n_results=top_k)
            return [
                [doc.page_content for doc in docs]
                for docs in docs_batch
            ]
        except Exception as e:
            print(f"Batch retrieval error: {e}")
            return [[] for _ in queries]

    def get_count(self) -> int:
        return self.db._collection.count()


retriever = Retriever()