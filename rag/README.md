# RAG Chatbot (Cloud-First)

This package powers the production chatbot with:

- Qdrant Cloud for vector retrieval
- Groq for answer generation
- Supabase Storage sync for document ingestion
- Flask web app in `web/`

## Quick Start

1. Install dependencies:
   ```bash
   pip install -r ../requirements_rag.txt
   ```

2. Configure environment variables (`.env` or system env):
   - `QDRANT_URL` and `QDRANT_API_KEY`
   - `GROQ_API_KEY` and optional `GROQ_MODEL`
   - `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, `SUPABASE_STORAGE_BUCKET`

3. Ingest documents into Qdrant (includes Supabase Storage sync):
   ```bash
   python -m rag.ingest --reset
   ```

4. Run the app:
   ```bash
   python ../web/app.py
   ```

## Ingestion Behavior

- By default, `rag.ingest` syncs supported files (`.pdf`, `.txt`, `.md`) from Supabase Storage into `data/docs` before chunking and indexing.
- Use `--skip-sync` to ingest only local files from `RAG_DOCS_DIR`.
- Text cache for lexical search is written to `data/text_cache`.

## Key Environment Variables

- `RAG_DATA_DIR` (default: `data`)
- `RAG_DOCS_DIR` (default: `data/docs`)
- `RAG_COLLECTION` (default: `ucu_docs`)
- `RAG_EMBED_MODEL` (default: `all-MiniLM-L6-v2`)
- `GROQ_MODEL` (default: `llama-3.1-8b-instant`)
- `RAG_CHUNK_SIZE` (default: `300`)
- `RAG_CHUNK_OVERLAP` (default: `60`)
- `RAG_TOP_K` (default: `6`)
- `RAG_LEXICAL_TOP_N` (default: `8`)
- `RAG_LEXICAL_MIN_HITS` (default: `1`)
- `RAG_OCR_ENABLED` (default: `false`)

## OCR for Scanned PDFs

```bash
sudo apt install -y tesseract-ocr poppler-utils
pip install -r ../requirements_rag.txt
export RAG_OCR_ENABLED=true
python -m rag.ingest --reset
```
