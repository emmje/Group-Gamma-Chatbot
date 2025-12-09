# Streamlit Setup Guide

## Error: Missing Dependencies

If you see this error:
```
ModuleNotFoundError: No module named 'sentence_transformers'
```

It means the required packages aren't installed in your Streamlit environment.

## Solution

### Option 1: Install in Your Current Environment

```bash
# Navigate to your project directory
cd /mount/src/group-gamma-chatbot/Notebooks

# Install dependencies
pip install -r requirements_zeroshot.txt
```

### Option 2: If Using a Virtual Environment

```bash
# Activate your virtual environment first
source /home/adminuser/venv/bin/activate

# Then install dependencies
pip install -r requirements_zeroshot.txt

# Run Streamlit
streamlit run app.py
```

### Option 3: Install Individual Packages

```bash
pip install sentence-transformers streamlit
```

## Verify Installation

Test that packages are installed:

```bash
python3 -c "from sentence_transformers import SentenceTransformer; print('✅ sentence-transformers installed')"
python3 -c "import streamlit; print('✅ streamlit installed')"
```

## Run Streamlit

After installing dependencies:

```bash
streamlit run app.py
```

## Common Issues

**"Permission denied"**
- Use `pip install --user -r requirements_zeroshot.txt`
- Or use sudo if you have permissions

**"pip not found"**
- Try `pip3` instead of `pip`
- Or `python3 -m pip install -r requirements_zeroshot.txt`

**"Still getting errors after installation"**
- Make sure you're installing in the same Python environment that Streamlit uses
- Check Python version: `python3 --version` (should be 3.8+)
- Restart Streamlit after installing packages

