#!/bin/bash
# Minimal setup script for Zero-Shot Chatbot only

echo "🚀 Setting up UCU Chatbot (Zero-Shot Only)..."
echo ""

SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
    echo "✅ Virtual environment created"
else
    echo "Virtual environment already exists"
fi

# Activate virtual environment
echo "Activating virtual environment..."
source venv/bin/activate

# Upgrade pip
echo "Upgrading pip..."
pip install --upgrade pip -q

# Install zero-shot requirements (includes Streamlit)
echo "Installing sentence-transformers and Streamlit..."
pip install -r requirements_zeroshot.txt

echo ""
echo "✅ Setup complete!"
echo ""
echo "To run the chatbot:"
echo ""
echo "Option 1: Streamlit Web Interface (Recommended)"
echo "1. Activate: source venv/bin/activate"
echo "2. Run: streamlit run app.py"
echo ""
echo "Option 2: Command Line Interface"
echo "1. Activate: source venv/bin/activate"
echo "2. Run: python3 chatbot_zeroshot.py"
echo ""
echo "That's it! No training needed."

