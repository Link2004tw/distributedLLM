import os
from typing import List
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document
from langchain_chroma import Chroma
from langchain_ollama import OllamaEmbeddings


EMBEDDING_MODEL = "nomic-embed-text"
CHROMA_DB_PATH = "./chroma_db"
COLLECTION_NAME = "documents"
DOCS_PATH = "./docs"


def load_documents() -> List[str]:
    documents = []
    if os.path.exists(DOCS_PATH):
        for filename in os.listdir(DOCS_PATH):
            if filename.endswith(".txt") or filename.endswith(".md"):
                filepath = os.path.join(DOCS_PATH, filename)
                with open(filepath, "r", encoding="utf-8") as f:
                    documents.append(f.read())
    else:
        documents = [
            "Python is a high-level programming language. It is interpreted and supports multiple programming paradigms.",
            "Machine learning is a subset of artificial intelligence that enables systems to learn from data without being explicitly programmed.",
            "Distributed systems are made up of multiple computers that communicate and coordinate to achieve a common goal.",
            "FastAPI is a modern Python web framework for building APIs with automatic Swagger documentation.",
            "ChromaDB is a vector database for storing and retrieving embeddings for AI applications.",
        ]
    return documents


def ingest_documents():
    print("Loading documents...")
    docs = load_documents()

    print("Splitting documents into chunks...")
    splitter = RecursiveCharacterTextSplitter(chunk_size=500, chunk_overlap=50)
    chunks = splitter.split_text("\n\n".join(docs))

    print(f"Creating {len(chunks)} chunks...")

    print(f"Loading embedding model: {EMBEDDING_MODEL}...")
    embeddings = OllamaEmbeddings(
        model=EMBEDDING_MODEL,
    )

    print(f"Creating/Updating ChromaDB at {CHROMA_DB_PATH}...")
    db = Chroma(
        persist_directory=CHROMA_DB_PATH,
        embedding_function=embeddings,
        collection_name=COLLECTION_NAME,
    )

    documents = [Document(page_content=chunk) for chunk in chunks]
    db.add_documents(documents)

    print(f"Successfully ingested {len(chunks)} document chunks into ChromaDB.")


if __name__ == "__main__":
    ingest_documents()