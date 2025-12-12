#!/bin/bash
# Simple dependency installer

echo "=========================================="
echo "Installing Chatbot Dependencies"
echo "=========================================="
echo ""

# Detect Python and pip
if command -v python3 &> /dev/null; then
    PYTHON="python3"
elif command -v python &> /dev/null; then
    PYTHON="python"
else
    echo "Error: Python not found!"
    exit 1
fi

if command -v pip3 &> /dev/null; then
    PIP="pip3"
elif command -v pip &> /dev/null; then
    PIP="pip"
else
    echo "Error: pip not found! Trying python -m pip..."
    PIP="$PYTHON -m pip"
fi

echo "Using: $PYTHON"
echo "Using: $PIP"
echo ""

# Check if we're in a virtual environment
if [ -n "$VIRTUAL_ENV" ]; then
    echo "Virtual environment detected: $VIRTUAL_ENV"
else
    echo "No virtual environment detected (this is okay)"
fi

echo ""
echo "Installing sentence-transformers..."
$PIP install sentence-transformers

echo ""
echo "Installing streamlit..."
$PIP install streamlit

echo ""
echo "=========================================="
echo "Installation Complete!"
echo "=========================================="
echo ""
echo "To verify, run:"
echo "  $PYTHON -c \"from sentence_transformers import SentenceTransformer; print('Ready!')\""
echo ""
echo "Then start Streamlit:"
echo "  streamlit run app.py"
echo ""

