# RAG Chatbot (New Implementation)

This folder contains the Retrieval-Augmented Generation (RAG) upgrade for the
university chatbot. It is separate from the legacy zero-shot version in
`Notebooks/`.

## What This Adds

- Document ingestion (PDF, TXT, MD) into a vector database
- Semantic retrieval using Chroma
- Local LLM generation via Ollama (e.g., `mistral`)
- A Gradio web UI in `web/`

## Quick Start

1. Install dependencies:
   ```bash
   pip install -r ../requirements_rag.txt
   ```

2. Add documents to `../data/docs/` (PDF, TXT, MD).

3. Ingest documents:
   ```bash
   python -m rag.ingest
   ```

4. Run the web UI:
   ```bash
   python ../web/app.py
   ```

## Project Structure

- `config.py` — configuration and environment variables
- `document_loaders.py` — load PDFs and text files
- `chunking.py` — split documents into overlapping chunks
- `embeddings.py` — sentence-transformer embeddings
- `vector_store.py` — Chroma vector database wrapper
- `generator.py` — Ollama LLM generation
- `pipeline.py` — retrieval + generation pipeline
- `ingest.py` — command-line ingestion pipeline

## Environment Variables (Optional)

- `RAG_DATA_DIR` (default: `data`)
- `RAG_DOCS_DIR` (default: `data/docs`)
- `RAG_CHROMA_DIR` (default: `data/chroma`)
- `RAG_COLLECTION` (default: `ucu_docs`)
- `RAG_EMBED_MODEL` (default: `all-MiniLM-L6-v2`)
- `RAG_LLM_MODEL` (default: `mistral`)
- `RAG_CHUNK_SIZE` (default: `300` words)
- `RAG_CHUNK_OVERLAP` (default: `60` words)
- `RAG_TOP_K` (default: `4`)
- `RAG_MAX_DISTANCE` (default: `1.1`)
- `RAG_OCR_ENABLED` (default: `false`)
- `RAG_LEXICAL_TOP_N` (default: `6`)
- `RAG_LEXICAL_MIN_HITS` (default: `1`)

## Notes

- Ollama must be running locally with the chosen model pulled.
- If you re-ingest, use `python -m rag.ingest --reset` to clear the collection.
- When retrieval confidence is low, the chatbot returns a human fallback response.
- See `metrics.md` for evaluation metrics and how to report them.

## OCR (Scanned PDFs)

If your PDFs are scanned images, enable OCR so text can be indexed:

```bash
sudo apt install -y tesseract-ocr poppler-utils
pip install -r ../requirements_rag.txt
export RAG_OCR_ENABLED=true
python -m rag.ingest --reset
```
