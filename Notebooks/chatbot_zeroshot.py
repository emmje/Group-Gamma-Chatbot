# chatbot_zeroshot.py
"""
UCU Chatbot using Zero-Shot Classification
This version uses sentence transformers for intent classification without training
Good for small datasets and when you want to add new intents without retraining
"""
import json
import random
import sys

try:
    from sentence_transformers import SentenceTransformer, util
    import torch
except ImportError as e:
    print("ERROR: Missing required packages!")
    print("Please install dependencies by running:")
    print("  pip install -r requirements_zeroshot.txt")
    print(f"\nMissing package: {e}")
    sys.exit(1)

# Path configuration
import os

# Get the directory where this script is located
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
INTENTS_FILE = os.path.join(SCRIPT_DIR, "intents.json")

# Global variables (will be initialized on first use)
_model = None
_intent_embeddings = None
_intent_responses = None
_intents_loaded = False

def reload_intents():
    """Reload intents from JSON file (useful after updating intents.json)"""
    global _intent_embeddings, _intent_responses, _intents_loaded
    _intent_embeddings = None
    _intent_responses = None
    _intents_loaded = False
    _initialize_model()

def _initialize_model():
    """Initialize model and embeddings (cached for Streamlit)"""
    global _model, _intent_embeddings, _intent_responses, _intents_loaded
    
    if _model is not None and _intents_loaded:
        return  # Already initialized
    
    # Load intents
    if not os.path.exists(INTENTS_FILE):
        raise FileNotFoundError(
            f"intents.json not found at {INTENTS_FILE}. "
            f"Current directory: {os.getcwd()}. "
            f"Script directory: {SCRIPT_DIR}. "
            f"Please ensure intents.json is in the same directory as chatbot_zeroshot.py"
        )
    
    with open(INTENTS_FILE, "r", encoding="utf-8") as f:
        intents = json.load(f)["intents"]

    # Initialize zero-shot model
    _model = SentenceTransformer('all-MiniLM-L6-v2')  # Lightweight, fast model

    # Pre-compute embeddings for all intent patterns
    _intent_embeddings = {}
    _intent_responses = {}

    for intent in intents:
        tag = intent["tag"]
        # Combine all patterns for this intent into a single representative text
        patterns_text = " ".join(intent["patterns"])
        embedding = _model.encode(patterns_text, convert_to_tensor=True)
        _intent_embeddings[tag] = embedding
        _intent_responses[tag] = intent["responses"]
    
    _intents_loaded = True

def get_response(user_input):
    """Get chatbot response using zero-shot classification"""
    # Initialize model if not already done
    _initialize_model()
    
    if not user_input.strip():
        return "I didn't understand that. Please try again."

    # Encode user input
    user_embedding = _model.encode(user_input, convert_to_tensor=True)
    
    # Find most similar intent
    best_tag = None
    best_similarity = 0.0
    
    for tag, intent_embedding in _intent_embeddings.items():
        similarity = util.cos_sim(user_embedding, intent_embedding).item()
        if similarity > best_similarity:
            best_similarity = similarity
            best_tag = tag
    
    # Confidence threshold
    if best_similarity < 0.3:  # Lower threshold for zero-shot
        return "I'm not very sure about that. Can you rephrase your question?"
    
    # Return random response from best matching intent
    if best_tag and best_tag in _intent_responses:
        return random.choice(_intent_responses[best_tag])
    
    return "I don't have a response for that yet. Please try asking something else."

if __name__ == "__main__":
    print("Loading UCU Chatbot...")
    _initialize_model()
    print(f"Loaded {len(_intent_embeddings)} intent categories")
    print("✅ Zero-shot chatbot ready!")
    print("=" * 50)
    print("UCU Chatbot (Zero-Shot) is ready! Type 'quit' to exit.")
    print("=" * 50)
    print()
    
    while True:
        msg = input("You: ")
        if msg.lower().strip() in ["quit", "exit", "bye"]:
            print("Bot: Goodbye! God bless you.")
            break
        response = get_response(msg)
        print(f"Bot: {response}")
        print()

