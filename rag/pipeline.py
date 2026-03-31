from __future__ import annotations

from pathlib import Path
from typing import List, Tuple

from .config import RagConfig, load_config
from .embeddings import EmbeddingModel
from .fallback import build_fallback_response
from .generator import generate_answer
from .lexical_search import lexical_search
from .vector_store import RetrievedChunk, VectorStore


def _source_to_title(source: str) -> str:
    """Derive a human-readable title from a file path."""
    return Path(source).stem.replace("_", " ").replace("-", " ").strip()


class RAGPipeline:
    def __init__(self, config: RagConfig | None = None) -> None:
        self.config = config or load_config()
        self.embedder = EmbeddingModel(self.config.embedding_model)
        self.store = VectorStore(
            self.config.qdrant_url,
            self.config.qdrant_api_key,
            self.config.collection_name,
            self.embedder,
        )

    def retrieve(self, question: str) -> List[RetrievedChunk]:
        """
        Combine semantic (vector) and lexical (keyword) search.
        Returns RetrievedChunk objects with metadata so the generator
        can cite which document each piece of context came from.
        """
        # 1) Semantic search from Qdrant (already returns RetrievedChunk)
        semantic_chunks = self.store.query(question, self.config.top_k)

        # 2) Lexical keyword search from text cache — wrap into RetrievedChunk
        lexical_lines = lexical_search(question, self.config)
        lexical_chunks: List[RetrievedChunk] = []
        for text, metadata in lexical_lines:
            source = metadata.get("source", "")
            title = _source_to_title(source) if source else ""
            lexical_chunks.append(
                RetrievedChunk(
                    text=text,
                    metadata={"source": source, "title": title},
                    distance=0.0,
                )
            )

        # 3) Interleave: alternate between semantic and lexical results
        #    so the LLM always gets the best of both search methods
        seen = set()
        merged: List[RetrievedChunk] = []
        si, li = 0, 0
        while len(merged) < 4 and (si < len(semantic_chunks) or li < len(lexical_chunks)):
            # Take one from semantic
            while si < len(semantic_chunks) and len(merged) < 4:
                key = semantic_chunks[si].text[:200]
                si += 1
                if key not in seen:
                    seen.add(key)
                    merged.append(semantic_chunks[si - 1])
                    break
            # Take one from lexical
            while li < len(lexical_chunks) and len(merged) < 4:
                key = lexical_chunks[li].text[:200]
                li += 1
                if key not in seen:
                    seen.add(key)
                    merged.append(lexical_chunks[li - 1])
                    break

        return merged

    def answer(self, question: str) -> str:
        context_chunks = self.retrieve(question)
        if not context_chunks:
            return build_fallback_response(question)
        return generate_answer(question, context_chunks, self.config.llm_model)
