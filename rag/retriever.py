from typing import List, Optional
import os
from langchain_chroma import Chroma
from langchain_huggingface import HuggingFaceEmbeddings


EMBEDDING_MODEL = "BAAI/bge-m3"
CHROMA_DB_PATH = "./chroma_db"
COLLECTION_NAME = "documents"


class Retriever:
    def __init__(self):
        self.embeddings = HuggingFaceEmbeddings(
            model=EMBEDDING_MODEL,
            model_kwargs={"device": "cpu"},
            encode_kwargs={"normalize_embeddings": True},
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


retriever = Retriever()