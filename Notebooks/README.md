# 🎓 UCU Chatbot - Zero-Shot with Streamlit Interface

A chatbot for Uganda Christian University using zero-shot classification with MiniLM-v2 and a beautiful Streamlit web interface.

## 🚀 Quick Start

### 1. Setup (One-time)

```bash
cd /home/nico/Downloads/Notebooks-20251124T065302Z-1-001/Notebooks
bash setup_zeroshot.sh
```

This will:
- Create a virtual environment
- Install sentence-transformers and Streamlit
- Set everything up

### 2. Run the Chatbot

**Option A: Web Interface (Recommended)**
```bash
source venv/bin/activate
streamlit run app.py
```

This will open a web browser with the chatbot interface.

**Option B: Command Line**
```bash
source venv/bin/activate
python3 chatbot_zeroshot.py
```

## 📁 Files

- `chatbot_zeroshot.py` - Zero-shot chatbot logic
- `app.py` - Streamlit web interface
- `intents.json` - Intent data and responses
- `requirements_zeroshot.txt` - Dependencies
- `setup_zeroshot.sh` - Setup script

## 🎯 Features

- ✅ Zero-shot classification (no training needed)
- ✅ Beautiful Streamlit web interface
- ✅ Chat history
- ✅ Fast responses
- ✅ Easy to add new intents

## 💡 Example Questions

- "Who is the vice chancellor of UCU?"
- "Where is Alan Galpin Health Centre?"
- "Where is Bishop Tucker Building?"
- "What are UCU's library opening hours?"
- "Hello"

## 🔧 Troubleshooting

**Streamlit not found:**
```bash
source venv/bin/activate
pip install streamlit
```

**Port already in use:**
```bash
streamlit run app.py --server.port 8502
```

**Model download issues:**
The first run will download the MiniLM-v2 model (~80MB). Make sure you have internet connection.

## 📝 Notes

- The chatbot uses semantic similarity to match user queries to intents
- No training required - just add new intents to `intents.json`
- The Streamlit interface automatically handles chat history

