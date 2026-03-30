from __future__ import annotations

import argparse
from pathlib import Path
from typing import List

from supabase import create_client

from .chunking import chunk_text
from .config import RagConfig, load_config
from .document_loaders import Document, load_documents
from .embeddings import EmbeddingModel
from .vector_store import VectorStore


def find_documents(docs_dir: Path) -> List[Path]:
    files: List[Path] = []
    for path in docs_dir.rglob("*"):
        if path.is_file() and path.suffix.lower() in {".pdf", ".txt", ".md"}:
            files.append(path)
    return files


def sync_documents_from_supabase(config: RagConfig) -> int:
    """
    Download documents from Supabase Storage to local docs_dir cache.
    Returns number of files downloaded/updated.
    """
    if not (
        config.supabase_url
        and config.supabase_service_key
        and config.supabase_storage_bucket
    ):
        return 0

    client = create_client(config.supabase_url, config.supabase_service_key)
    bucket = client.storage.from_(config.supabase_storage_bucket)

    prefix = config.supabase_storage_prefix.strip("/")
    queue = [prefix] if prefix else [""]
    downloaded = 0

    while queue:
        current_path = queue.pop(0)
        entries = bucket.list(path=current_path)
        for entry in entries or []:
            name = entry.get("name")
            if not name:
                continue

            remote_path = f"{current_path}/{name}" if current_path else name
            remote_path = remote_path.strip("/")

            # Try file download first; if this fails, treat as folder and recurse.
            try:
                content = bucket.download(remote_path)
            except Exception:
                queue.append(remote_path)
                continue

            suffix = Path(remote_path).suffix.lower()
            if suffix not in {".pdf", ".txt", ".md"}:
                continue

            target = config.docs_dir / remote_path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)
            downloaded += 1

    return downloaded


def prepare_chunks(documents: List[Document], config: RagConfig) -> List[Document]:
    chunked_documents: List[Document] = []
    for doc in documents:
        chunks = chunk_text(doc.text, config.chunk_size, config.chunk_overlap)
        for chunk_index, chunk in enumerate(chunks, start=1):
            metadata = dict(doc.metadata)
            metadata["chunk"] = chunk_index
            chunked_documents.append(Document(text=chunk, metadata=metadata))
    return chunked_documents


def write_text_cache(documents: List[Document], config: RagConfig) -> None:
    cache_dir = config.data_dir / "text_cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    by_source: dict[str, list[str]] = {}
    for doc in documents:
        source = doc.metadata.get("source")
        if not source:
            continue
        by_source.setdefault(source, []).append(doc.text)
    for source, texts in by_source.items():
        stem = Path(source).stem
        cache_path = cache_dir / f"{stem}.txt"
        combined = "\n".join(texts)
        cache_path.write_text(combined, encoding="utf-8")


def ingest(config: RagConfig, reset: bool = False, sync: bool = True) -> int:
    config.docs_dir.mkdir(parents=True, exist_ok=True)

    if sync:
        synced = sync_documents_from_supabase(config)
        if synced:
            print(f"Synced {synced} document(s) from Supabase Storage.")

    files = find_documents(config.docs_dir)
    if not files:
        raise FileNotFoundError(
            f"No documents found in {config.docs_dir}. "
            "Add PDFs or text files before ingesting."
        )

    documents = load_documents(files, enable_ocr=config.enable_ocr)
    write_text_cache(documents, config)
    chunked_documents = prepare_chunks(documents, config)

    embedder = EmbeddingModel(config.embedding_model)
    store = VectorStore(config.qdrant_url, config.qdrant_api_key, config.collection_name, embedder)

    if reset:
        store.reset(config.collection_name)

    texts = [doc.text for doc in chunked_documents]
    metadatas = [doc.metadata for doc in chunked_documents]
    store.add_texts(texts, metadatas)

    return len(texts)


def main() -> None:
    parser = argparse.ArgumentParser(description="Ingest documents into Qdrant.")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Delete existing collection before ingesting.",
    )
    parser.add_argument(
        "--skip-sync",
        action="store_true",
        help="Skip Supabase Storage sync and ingest only local files.",
    )
    args = parser.parse_args()

    config = load_config()
    total = ingest(config, reset=args.reset, sync=not args.skip_sync)
    print(f"Ingested {total} chunks into '{config.collection_name}'.")


if __name__ == "__main__":
    main()
