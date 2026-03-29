# Gamma Chatbot Project

This repository contains two versions of the university chatbot:

1. **Legacy zero-shot chatbot (December baseline)**  
   Located in `Notebooks/`. It uses intent matching with sentence-transformers and a
   Streamlit interface.

2. **RAG-based chatbot (new implementation)**  
   Located in `rag/` and `web/`. It uses Qdrant retrieval, Groq LLM generation,
   Supabase Postgres + Storage, and a Flask app.

## Production Stack (Implemented)

- **Backend hosting:** Oracle Cloud Always Free VM
- **Main database:** Supabase Postgres (`DATABASE_URL`)
- **Vector database:** Qdrant Cloud
- **LLM:** Groq API
- **Document storage:** Supabase Storage

## RAG Quick Start

1. Install dependencies:
   ```bash
   pip install -r requirements_rag.txt
   ```

2. Add documents (PDF, TXT, MD) to `data/docs/`.

3. Sync and ingest documents from Supabase Storage into Qdrant:
   ```bash
   python -m rag.ingest
   ```

4. Run the web app:
   ```bash
   python web/app.py
   ```

## Deploy on Render

This repository includes [render.yaml](render.yaml) for one-click Blueprint deployment.

1. Push the branch to GitHub.
2. In Render, choose **New +** → **Blueprint** and select this repo.
3. Render creates `gamma-chatbot` using `render.yaml`.
4. In Render service **Environment**, set all `sync: false` variables (secrets).
5. After first deploy, copy the service URL (example: `https://gamma-chatbot.onrender.com`).
6. Set `PUBLIC_BASE_URL` to that exact URL and redeploy.
7. Attach a persistent disk and mount it at `/var/data` so user accounts survive redeploys.

Account persistence notes:

- The app stores auth data in `GAMMA_DB_PATH` (default in Render blueprint: `/var/data/gamma.db`).
- A backup mirror is kept at `GAMMA_USERS_BACKUP_PATH` (default: `/var/data/users_backup.json`).
- On startup, users are restored from backup and optional legacy DB paths (`GAMMA_LEGACY_DB_PATHS`).
- If a configured storage path is not writable, the app falls back to `data/gamma.db` to stay available.

Render Free plan recommendation:

- If your plan does not support disks, set `DATABASE_URL` to Supabase/Postgres.
- Auth accounts (login/signup) will use Postgres as the primary store when `DATABASE_URL` is available.
- On startup, local SQLite users and backup users are migrated into Postgres automatically.
- If Postgres is temporarily unreachable, signup/login falls back to SQLite so the app remains usable.

Public legal URLs become:

- `https://<your-render-host>/terms`
- `https://<your-render-host>/privacy`
- `https://<your-render-host>/data-deletion`

For Meta App setup:

- App Domains: `<your-render-host-without-https>`
- Privacy Policy URL: `https://<your-render-host>/privacy`
- Terms of Service URL: `https://<your-render-host>/terms`
- User Data Deletion URL: `https://<your-render-host>/data-deletion`

## Environment Variables

- `RAG_DATA_DIR` (default: `data`)
- `RAG_DOCS_DIR` (default: `data/docs`)
- `RAG_COLLECTION` (default: `ucu_docs`, used as Qdrant collection)
- `RAG_EMBED_MODEL` (default: `all-MiniLM-L6-v2`)
- `GROQ_API_KEY` (**required**)
- `GROQ_MODEL` (default: `llama-3.1-8b-instant`)
- `GROQ_BASE_URL` (optional override)
- `RAG_CHUNK_SIZE` (default: `300` words)
- `RAG_CHUNK_OVERLAP` (default: `60` words)
- `RAG_TOP_K` (default: `6`)
- `RAG_MAX_DISTANCE` (default: `1.1`)
- `RAG_OCR_ENABLED` (default: `false`)
- `RAG_LEXICAL_TOP_N` (default: `8`)
- `RAG_LEXICAL_MIN_HITS` (default: `1`)
- `DATABASE_URL` (**required**, Supabase Postgres connection string)
- `QDRANT_URL` (**required**)
- `QDRANT_API_KEY` (required for private Qdrant Cloud instances)
- `SUPABASE_URL` (for storage sync)
- `SUPABASE_SERVICE_KEY` (for storage sync)
- `SUPABASE_STORAGE_BUCKET` (default: empty, set to your docs bucket)
- `SUPABASE_STORAGE_PREFIX` (optional path prefix inside bucket)
- `FLASK_SECRET_KEY` (**required in production**)
- `GAMMA_DB_PATH` (optional override for SQLite DB path; use persistent disk path in production)
- `GAMMA_USERS_BACKUP_PATH` (optional path for portable user backup JSON)
- `GAMMA_LEGACY_DB_PATHS` (optional comma-separated old DB paths to migrate users from)
- `GAMMA_BOOTSTRAP_ADMIN_USERNAME` (optional admin account seed username)
- `GAMMA_BOOTSTRAP_ADMIN_PASSWORD` (optional admin account seed password)
- `PUBLIC_BASE_URL` (required for generating/shareable public legal URLs, e.g. `https://chatbot.example.com`)
- `SUNBIRD_API_KEY` (required for Sunbird translation, TTS, STT)
- `SUNBIRD_BASE_URL` (default: `https://api.sunbird.ai`)
- `SUNBIRD_TRANSLATE_ENDPOINT` (default: `/tasks/translate`)
- `SUNBIRD_TTS_ENDPOINT` (default: `/tasks/modal/tts`)
- `SUNBIRD_STT_ENDPOINT` (default: `/tasks/modal/stt`)
- `SUNBIRD_TIMEOUT_SECONDS` (default: `120`)

## OCR (for scanned PDFs)

Some PDFs are scanned images and contain no selectable text. Enable OCR if you
need those documents indexed:

```bash
sudo apt install -y tesseract-ocr poppler-utils
pip install -r requirements_rag.txt
export RAG_OCR_ENABLED=true
python -m rag.ingest --reset
```

## WhatsApp Business API (Meta Cloud API)

The Flask app includes WhatsApp webhook integration via Meta Business (Cloud API).

Set environment variables before starting the app:

```bash
export META_GRAPH_BASE_URL="https://graph.facebook.com"
export META_GRAPH_API_VERSION="v20.0"
export META_WHATSAPP_ACCESS_TOKEN="<your-meta-whatsapp-access-token>"
export META_WHATSAPP_PHONE_NUMBER_ID="<your-phone-number-id>"
export META_WHATSAPP_VERIFY_TOKEN="<your-webhook-verify-token>"
# optional shared secret header check for webhook protection
export META_WHATSAPP_WEBHOOK_TOKEN="<random-shared-secret>"
```

Available endpoints:

- `GET /api/whatsapp/status` — quick health/config check
- `GET /webhooks/meta/whatsapp` — Meta webhook verification callback
- `POST /webhooks/meta/whatsapp` — inbound WhatsApp webhook from Meta

Flow:

1. Meta sends webhook verification and inbound WhatsApp events to `/webhooks/meta/whatsapp`.
2. The app runs the RAG pipeline to generate an answer.
3. The app sends the answer back to the same number through Meta WhatsApp Cloud API.

Security note:

- Keep API keys in environment variables only.
- Rotate any key that has been shared in chat/history.

Meta App Review URLs (required for WhatsApp integration):

- Terms of Service URL: `https://<your-public-domain>/terms`
- Privacy Policy URL: `https://<your-public-domain>/privacy`
- User data deletion URL: `https://<your-public-domain>/data-deletion`

These endpoints are implemented in the Flask app and must be reachable publicly over HTTPS.

## Sunbird AI Integration

This project now includes backend endpoints that proxy Sunbird AI services:

- `GET /api/sunbird/status`
- `POST /api/sunbird/translate` (JSON: `text`, `source_language`, `target_language`)
- `POST /api/sunbird/tts` (JSON: `text`, optional `speaker_id`, `response_mode`, `temperature`, `max_new_audio_tokens`)
- `POST /api/sunbird/stt` (multipart form-data with `audio`, optional `language`, `adapter`, `whisper`, `recognise_speakers`)

All Sunbird endpoints require app login (`@login_required`).

