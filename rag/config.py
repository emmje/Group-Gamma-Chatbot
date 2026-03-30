from dataclasses import dataclass
from pathlib import Path
import os

from dotenv import dotenv_values, load_dotenv

# Project root: the directory containing the rag/ package
_PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Load .env values for local development and CLI usage.
load_dotenv(_PROJECT_ROOT / ".env", override=False)
_DOTENV_VALUES = dotenv_values(_PROJECT_ROOT / ".env")


def _get_env(name: str, default: str = "") -> str:
    value = os.getenv(name)
    if value is not None and value.strip() != "":
        return value.strip()
    dotenv_value = _DOTENV_VALUES.get(name)
    if isinstance(dotenv_value, str) and dotenv_value.strip() != "":
        return dotenv_value.strip()
    return default


@dataclass(frozen=True)
class RagConfig:
    data_dir: Path
    docs_dir: Path
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
    qdrant_url: str
    qdrant_api_key: str
    supabase_url: str
    supabase_service_key: str
    supabase_storage_bucket: str
    supabase_storage_prefix: str
    groq_api_key: str
    groq_base_url: str


def load_config() -> RagConfig:
    default_data = _PROJECT_ROOT / "data"
    data_dir = Path(_get_env("RAG_DATA_DIR", str(default_data)))
    docs_dir = Path(_get_env("RAG_DOCS_DIR", str(data_dir / "docs")))

    return RagConfig(
        data_dir=data_dir,
        docs_dir=docs_dir,
        collection_name=_get_env("RAG_COLLECTION", "ucu_docs"),
        embedding_model=_get_env("RAG_EMBED_MODEL", "all-MiniLM-L6-v2"),
        llm_model=_get_env("GROQ_MODEL", _get_env("RAG_LLM_MODEL", "llama-3.1-8b-instant")),
        chunk_size=int(_get_env("RAG_CHUNK_SIZE", "300")),
        chunk_overlap=int(_get_env("RAG_CHUNK_OVERLAP", "60")),
        top_k=int(_get_env("RAG_TOP_K", "6")),
        max_distance=float(_get_env("RAG_MAX_DISTANCE", "1.1")),
        enable_ocr=_get_env("RAG_OCR_ENABLED", "false").lower() == "true",
        lexical_top_n=int(_get_env("RAG_LEXICAL_TOP_N", "8")),
        lexical_min_hits=int(_get_env("RAG_LEXICAL_MIN_HITS", "1")),
        qdrant_url=_get_env("QDRANT_URL"),
        qdrant_api_key=_get_env("QDRANT_API_KEY"),
        supabase_url=_get_env("SUPABASE_URL"),
        supabase_service_key=_get_env("SUPABASE_SERVICE_KEY"),
        supabase_storage_bucket=_get_env("SUPABASE_STORAGE_BUCKET"),
        supabase_storage_prefix=_get_env("SUPABASE_STORAGE_PREFIX"),
        groq_api_key=_get_env("GROQ_API_KEY"),
        groq_base_url=_get_env("GROQ_BASE_URL", "https://api.groq.com"),
    )
