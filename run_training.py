from train_intent_classifier import train_model
from intent_classifier import test_classifier
from config import config
import os

def main():
    # Check if intents.json exists in current directory
    print("Looking for intents.json in current directory...")
    
    if not os.path.exists(config.DATA_PATH):
        print(f"ERROR: {config.DATA_PATH} not found in current directory!")
        print("Current directory files:")
        for file in os.listdir('.'):
            print(f" - {file}")
        return
    
    print(f"Found intents.json in current directory")
    
    # Train the model
    print("Starting model training...")
    model, tokenizer, tag_mapping = train_model()
    
    # Test the classifier
    print("\nTesting the trained classifier...")
    test_classifier()
    
    print(f"\nModel saved to: {config.SAVE_PATH}")
    print("Training completed successfully!")

if __name__ == "__main__":
    main()