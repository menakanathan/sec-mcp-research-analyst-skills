import json
import os
from pathlib import Path

import numpy as np
from openai import OpenAI


INDEX_DIR = Path("rag_indexes")
INDEX_DIR.mkdir(exist_ok=True)


def chunk_text(text, chunk_size=1800, overlap=250):
    chunks = []
    start = 0
    chunk_id = 1

    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end].strip()

        if chunk:
            chunks.append({
                "chunk_id": chunk_id,
                "text": chunk
            })

        start = end - overlap
        chunk_id += 1

    return chunks


def get_embedding(text):
    api_key = os.getenv("OPENAI_API_KEY")

    if not api_key:
        raise ValueError("OPENAI_API_KEY is required for RAG embeddings.")

    client = OpenAI(api_key=api_key)

    response = client.embeddings.create(
        model="text-embedding-3-small",
        input=text
    )

    return response.data[0].embedding


def cosine_similarity(vec1, vec2):
    a = np.array(vec1)
    b = np.array(vec2)

    denominator = np.linalg.norm(a) * np.linalg.norm(b)

    if denominator == 0:
        return 0.0

    return float(np.dot(a, b) / denominator)


def get_index_path(ticker, form_type):
    return INDEX_DIR / f"{ticker.upper()}_{form_type.upper()}_rag_index.json"


def build_rag_index(ticker, form_type, filing_text, metadata):
    chunks = chunk_text(filing_text)

    api_key = os.getenv("OPENAI_API_KEY")

    if not api_key:
        raise ValueError("OPENAI_API_KEY is required.")

    client = OpenAI(api_key=api_key)

    chunk_texts = [chunk["text"] for chunk in chunks]

    response = client.embeddings.create(
        model="text-embedding-3-small",
        input=chunk_texts
    )

    indexed_chunks = []

    for chunk, embedding_data in zip(chunks, response.data):
        indexed_chunks.append({
            "chunk_id": chunk["chunk_id"],
            "text": chunk["text"],
            "embedding": embedding_data.embedding
        })

    """
    indexed_chunks = []

    for chunk in chunks:
        embedding = get_embedding(chunk["text"])

        indexed_chunks.append({
            "chunk_id": chunk["chunk_id"],
            "text": chunk["text"],
            "embedding": embedding
        })
    """
    index = {
        "ticker": ticker.upper(),
        "form_type": form_type.upper(),
        "metadata": metadata,
        "chunk_count": len(indexed_chunks),
        "chunks": indexed_chunks
    }

    index_path = get_index_path(ticker, form_type)

    with open(index_path, "w", encoding="utf-8") as file:
        json.dump(index, file)

    return {
        "ticker": ticker.upper(),
        "form_type": form_type.upper(),
        "index_path": str(index_path),
        "chunk_count": len(indexed_chunks),
        "metadata": metadata
    }


def load_rag_index(ticker, form_type):
    index_path = get_index_path(ticker, form_type)

    if not index_path.exists():
        return None

    with open(index_path, "r", encoding="utf-8") as file:
        return json.load(file)


def semantic_search(ticker, form_type, query, top_k=5):
    index = load_rag_index(ticker, form_type)

    if not index:
        return {
            "error": "RAG index not found. Build the RAG index first.",
            "ticker": ticker.upper(),
            "form_type": form_type.upper(),
            "results": []
        }

    query_embedding = get_embedding(query)

    scored_chunks = []

    for chunk in index["chunks"]:
        score = cosine_similarity(query_embedding, chunk["embedding"])

        scored_chunks.append({
            "chunk_id": chunk["chunk_id"],
            "similarity_score": round(score, 4),
            "text": chunk["text"]
        })

    scored_chunks = sorted(
        scored_chunks,
        key=lambda x: x["similarity_score"],
        reverse=True
    )

    return {
        "ticker": ticker.upper(),
        "form_type": form_type.upper(),
        "metadata": index.get("metadata", {}),
        "query": query,
        "results": scored_chunks[:top_k]
    }