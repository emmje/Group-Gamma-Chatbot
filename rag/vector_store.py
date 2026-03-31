from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List
from uuid import uuid4

from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels

from .embeddings import EmbeddingModel


@dataclass
class RetrievedChunk:
    text: str
    metadata: Dict[str, Any]
    distance: float


class VectorStore:
    def __init__(
        self,
        qdrant_url: str,
        qdrant_api_key: str,
        collection_name: str,
        embedder: EmbeddingModel,
    ) -> None:
        if not qdrant_url:
            raise RuntimeError("QDRANT_URL is required for vector storage.")

        self.client = QdrantClient(
            url=qdrant_url,
            api_key=qdrant_api_key or None,
            timeout=30,
        )
        self.collection_name = collection_name
        self.embedder = embedder
        self._ensure_collection()

    def _ensure_collection(self) -> None:
        collections = self.client.get_collections().collections
        names = {collection.name for collection in collections}
        if self.collection_name in names:
            return
        self.client.create_collection(
            collection_name=self.collection_name,
            vectors_config=qmodels.VectorParams(
                size=self.embedder.dimension,
                distance=qmodels.Distance.COSINE,
            ),
        )

    def reset(self, collection_name: str) -> None:
        self.collection_name = collection_name
        self.client.delete_collection(collection_name=collection_name)
        self._ensure_collection()

    def add_texts(self, texts: List[str], metadatas: List[Dict[str, Any]]) -> None:
        ids = [str(metadata.get("id", uuid4())) for metadata in metadatas]
        embeddings = self.embedder.embed_texts(texts)
        points: List[qmodels.PointStruct] = []
        for point_id, text, metadata, vector in zip(ids, texts, metadatas, embeddings):
            payload = {"text": text, **(metadata or {})}
            points.append(
                qmodels.PointStruct(
                    id=point_id,
                    vector=vector,
                    payload=payload,
                )
            )
        self.client.upsert(
            collection_name=self.collection_name,
            points=points,
        )

    def query(
        self,
        query_text: str,
        top_k: int,
        where: Dict[str, Any] | None = None,
    ) -> List[RetrievedChunk]:
        query_embedding = self.embedder.embed_query(query_text)
        query_filter = None
        if where:
            must: List[qmodels.FieldCondition] = []
            for key, value in where.items():
                must.append(
                    qmodels.FieldCondition(
                        key=key,
                        match=qmodels.MatchValue(value=value),
                    )
                )
            query_filter = qmodels.Filter(must=must)

        if hasattr(self.client, "search"):
            results = self.client.search(
                collection_name=self.collection_name,
                query_vector=query_embedding,
                query_filter=query_filter,
                limit=top_k,
                with_payload=True,
                with_vectors=False,
            )
        else:
            query_response = self.client.query_points(
                collection_name=self.collection_name,
                query=query_embedding,
                query_filter=query_filter,
                limit=top_k,
                with_payload=True,
                with_vectors=False,
            )
            results = getattr(query_response, "points", query_response)

        retrieved: List[RetrievedChunk] = []
        for point in results:
            payload = dict(point.payload or {})
            text = str(payload.pop("text", ""))
            score = float(point.score or 0.0)
            retrieved.append(
                RetrievedChunk(
                    text=text,
                    metadata=payload,
                    distance=1.0 - score,
                )
            )
        return retrieved
