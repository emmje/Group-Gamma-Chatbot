#!/bin/bash
# Quick dependency installer for UCU Chatbot Streamlit app

echo "Installing dependencies..."
echo ""

# Check if pip is available
if ! command -v pip &> /dev/null && ! command -v pip3 &> /dev/null; then
    echo "Error: pip not found. Please install pip first."
    exit 1
fi

# Use pip3 if available, otherwise pip
PIP_CMD="pip3"
if ! command -v pip3 &> /dev/null; then
    PIP_CMD="pip"
fi

echo "Using: $PIP_CMD"
echo ""

# Install from requirements file if it exists
if [ -f "requirements_zeroshot.txt" ]; then
    echo "Installing from requirements_zeroshot.txt..."
    $PIP_CMD install -r requirements_zeroshot.txt
else
    echo "requirements_zeroshot.txt not found. Installing packages directly..."
    $PIP_CMD install sentence-transformers streamlit
fi

echo ""
echo "Installation complete!"
echo ""
echo "  streamlit run app.py"

