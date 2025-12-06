# Zero-Shot Chatbot - Minimal Setup

If you're **only using the zero-shot approach** (MiniLM-v2), you only need these files:

## Required Files

✅ **Essential:**
- `chatbot_zeroshot.py` - The main chatbot script
- `intents.json` - Your intent data
- `requirements_zeroshot.txt` - Minimal dependencies

❌ **NOT Needed:**
- `preprocess.py` - Sentence-transformers handles preprocessing
- `model.py` - Using pre-trained model, not custom
- `train.py` - No training required
- `chatbot.py` - That's for the traditional approach
- `nltkdownload.py` - NLTK not used
- `saved/` directory - No saved models needed

## Quick Setup

```bash
cd /home/nico/Downloads/Notebooks-20251124T065302Z-1-001/Notebooks
bash setup_zeroshot.sh
```

Or manually:

```bash
python3 -m venv venv
source venv/bin/activate
pip install sentence-transformers
```

## Run It

```bash
source venv/bin/activate
python3 chatbot_zeroshot.py
```

## What Gets Installed

- `sentence-transformers` - The zero-shot model library
- `torch` - Automatically installed as dependency (PyTorch)
- `transformers` - Automatically installed as dependency

That's it! Much simpler than the full setup.

## File Size Comparison

**Full setup (traditional + zero-shot):**
- ~500MB+ (torch, sklearn, nltk, etc.)

**Zero-shot only:**
- ~200MB (sentence-transformers + torch)

## How It Works

1. Loads `intents.json`
2. Downloads pre-trained MiniLM-v2 model (first run only)
3. Creates embeddings for each intent's patterns
4. Compares user input to intent embeddings using cosine similarity
5. Returns response from best matching intent

No training, no preprocessing, no custom models needed!

