# 🚀 START HERE - Get Your Chatbot Running!

## Step 1: Setup (One-time only)

```bash
cd /home/nico/Downloads/Notebooks-20251124T065302Z-1-001/Notebooks
bash setup_zeroshot.sh
```

This installs everything you need. It will take a few minutes the first time (downloads the model).

## Step 2: Run the Streamlit Web Interface

```bash
source venv/bin/activate
streamlit run app.py
```

Your browser will automatically open with the chatbot interface! 🎉

## That's It!

You now have:
- ✅ A working zero-shot chatbot
- ✅ A beautiful Streamlit web interface
- ✅ Chat history
- ✅ No training required!

## Alternative: Command Line Interface

If you prefer command line instead of web interface:

```bash
source venv/bin/activate
python3 chatbot_zeroshot.py
```

## Troubleshooting

**"command not found: streamlit"**
```bash
source venv/bin/activate
pip install streamlit
```

**Port 8501 already in use:**
```bash
streamlit run app.py --server.port 8502
```

**Model download slow?**
- First run downloads ~80MB model
- Subsequent runs are instant
- Make sure you have internet connection

## Next Steps

- Try asking questions about UCU
- Customize the interface in `app.py`
- Add new intents to `intents.json` (no retraining needed!)

