from dataclasses import dataclass
from pathlib import Path
import os

# Project root: the directory containing the rag/ package
_PROJECT_ROOT = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class RagConfig:
    data_dir: Path
    docs_dir: Path
    chroma_dir: Path
    collection_name: str
    embedding_model: str
    llm_model: str
    chunk_size: int
    chunk_overlap: int
    top_k: int
    max_distance: float
    enable_ocr: bool
    lexical_top_n: int
    lexical_min_hits: int


def load_config() -> RagConfig:
    default_data = _PROJECT_ROOT / "data"
    data_dir = Path(os.getenv("RAG_DATA_DIR", str(default_data)))
    docs_dir = Path(os.getenv("RAG_DOCS_DIR", str(data_dir / "docs")))
    chroma_dir = Path(os.getenv("RAG_CHROMA_DIR", str(data_dir / "chroma")))

    return RagConfig(
        data_dir=data_dir,
        docs_dir=docs_dir,
        chroma_dir=chroma_dir,
        collection_name=os.getenv("RAG_COLLECTION", "ucu_docs"),
        embedding_model=os.getenv("RAG_EMBED_MODEL", "all-MiniLM-L6-v2"),
        llm_model=os.getenv("RAG_LLM_MODEL", "phi3:mini"),
        chunk_size=int(os.getenv("RAG_CHUNK_SIZE", "300")),
        chunk_overlap=int(os.getenv("RAG_CHUNK_OVERLAP", "60")),
        top_k=int(os.getenv("RAG_TOP_K", "6")),
        max_distance=float(os.getenv("RAG_MAX_DISTANCE", "1.1")),
        enable_ocr=os.getenv("RAG_OCR_ENABLED", "false").lower() == "true",
        lexical_top_n=int(os.getenv("RAG_LEXICAL_TOP_N", "8")),
        lexical_min_hits=int(os.getenv("RAG_LEXICAL_MIN_HITS", "1")),
    )
