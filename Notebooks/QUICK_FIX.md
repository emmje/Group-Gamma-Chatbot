# 🚨 Quick Fix for Streamlit Error

## The Problem
You're seeing: `ModuleNotFoundError: No module named 'sentence_transformers'`

This means dependencies aren't installed in your Streamlit environment.

## The Solution (Choose One)

### Option 1: Run Install Script (Easiest)
```bash
cd /mount/src/group-gamma-chatbot/Notebooks
bash install_dependencies.sh
```

### Option 2: Manual Install
```bash
cd /mount/src/group-gamma-chatbot/Notebooks
pip install -r requirements_zeroshot.txt
```

### Option 3: Install Individual Packages
```bash
pip install sentence-transformers streamlit
```

### Option 4: If Using Virtual Environment
```bash
source /home/adminuser/venv/bin/activate
pip install sentence-transformers streamlit
```

## After Installing

1. **Restart Streamlit** (stop with Ctrl+C, then restart)
2. **Refresh your browser**

## Verify It Worked

Run this to test:
```bash
python3 -c "from sentence_transformers import SentenceTransformer; print('✅ Ready!')"
```

If you see ✅ Ready!, then run Streamlit again:
```bash
streamlit run app.py
```

## Still Having Issues?

Check:
- Are you in the right directory? (`/mount/src/group-gamma-chatbot/Notebooks`)
- Is pip installed? (`pip --version`)
- Are you using the right Python? (`which python3`)
- Try: `python3 -m pip install sentence-transformers streamlit`

