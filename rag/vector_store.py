from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List
from uuid import uuid4

import chromadb

from .embeddings import EmbeddingModel


@dataclass
class RetrievedChunk:
    text: str
    metadata: Dict[str, Any]
    distance: float


class VectorStore:
    def __init__(
        self,
        persist_dir: Path,
        collection_name: str,
        embedder: EmbeddingModel,
    ) -> None:
        self.client = chromadb.PersistentClient(path=str(persist_dir))
        self.collection = self.client.get_or_create_collection(name=collection_name)
        self.embedder = embedder

    def reset(self, collection_name: str) -> None:
        self.client.delete_collection(name=collection_name)
        self.collection = self.client.get_or_create_collection(name=collection_name)

    def add_texts(self, texts: List[str], metadatas: List[Dict[str, Any]]) -> None:
        ids = [str(metadata.get("id", uuid4())) for metadata in metadatas]
        embeddings = self.embedder.embed_texts(texts)
        self.collection.add(
            documents=texts,
            metadatas=metadatas,
            ids=ids,
            embeddings=embeddings,
        )

    def query(
        self,
        query_text: str,
        top_k: int,
        where: Dict[str, Any] | None = None,
    ) -> List[RetrievedChunk]:
        query_embedding = self.embedder.embed_query(query_text)
        kwargs: Dict[str, Any] = {
            "query_embeddings": [query_embedding],
            "n_results": top_k,
            "include": ["documents", "metadatas", "distances"],
        }
        if where is not None:
            kwargs["where"] = where
        results = self.collection.query(**kwargs)

        documents = results.get("documents", [[]])[0]
        metadatas = results.get("metadatas", [[]])[0]
        distances = results.get("distances", [[]])[0]

        retrieved: List[RetrievedChunk] = []
        for text, metadata, distance in zip(documents, metadatas, distances):
            retrieved.append(
                RetrievedChunk(text=text, metadata=metadata or {}, distance=distance)
            )
        return retrieved
